import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import grafico_diario as diario
from resumen_trafico import comparar_historico, resumir_sentido

FECHA = datetime(2026, 9, 7)


def puntos(*medidas):
    return [(datetime.fromisoformat(f"2026-09-07 {hora}"), minutos) for hora, minutos in medidas]


def dia(minutos=20, cantidad=32, inicio=8):
    return [(FECHA.replace(hour=inicio) + timedelta(minutes=15 * i), minutos) for i in range(cantidad)]


class ResumenTests(unittest.TestCase):
    def test_cambio_local_real_trocadero(self):
        resultado = resumir_sentido(puntos(("08:30", 49), ("08:45", 62), ("09:00", 58), ("09:15", 48)))
        self.assertIn("08:45 (62 min) → 09:15 (48 min)", resultado)
        self.assertIn("14 min menos de trayecto saliendo 30 min después", resultado)

    def test_empeoramiento_y_retraso_del_recolector(self):
        resultado = resumir_sentido(puntos(("16:00", 20), ("16:31", 27)))
        self.assertIn("7 min más de trayecto saliendo 31 min después", resultado)

    def test_no_compara_horas_lejanas_ni_reintentos(self):
        resultado = resumir_sentido(puntos(("08:00", 60), ("08:01", 45), ("23:00", 20)))
        self.assertNotIn("después", resultado)

    def test_franja_estable_continua(self):
        resultado = resumir_sentido(puntos(("14:00", 21), ("14:15", 20), ("14:30", 22), ("14:45", 21)))
        self.assertIn("estables de 14:00 a 14:45: 20–22 min", resultado)

    def test_huecos_no_crean_franja_estable(self):
        resultado = resumir_sentido(puntos(("14:00", 21), ("14:15", 21), ("15:00", 21), ("15:15", 21)))
        self.assertNotIn("tiempos estables", resultado)

    def test_datos_escasos_y_duplicados(self):
        self.assertEqual(resumir_sentido([]), "sin medidas.")
        self.assertIn("solo una medida", resumir_sentido(puntos(("08:00", 20), ("08:00", 20))))

    def historico(self, cantidad=3, minutos=20):
        return {(FECHA - timedelta(weeks=n)).date(): {"ida": dia(minutos), "vuelta": dia(minutos)}
                for n in range(1, cantidad + 1)}

    def test_compara_mismo_sentido_y_horas(self):
        resultado = comparar_historico({"ida": dia(25), "vuelta": dia(15)}, self.historico(), FECHA)
        self.assertIn("ida: 5 min más frente a 3 lunes previos", resultado)
        self.assertIn("vuelta: 5 min menos frente a 3 lunes previos", resultado)

    def test_no_compara_horas_distintas(self):
        resultado = comparar_historico({"ida": dia(25, inicio=16), "vuelta": []}, self.historico(), FECHA)
        self.assertIn("ida: histórico insuficiente", resultado)

    def test_exige_tres_dias_y_cobertura(self):
        for datos, historico in [({"ida": dia(), "vuelta": []}, self.historico(2)),
                                 ({"ida": dia(cantidad=4), "vuelta": []}, self.historico())]:
            with self.subTest(datos=datos):
                self.assertIn("ida: histórico insuficiente", comparar_historico(datos, historico, FECHA))

    def test_excluye_dia_actual_futuro_y_otro_dia_de_semana(self):
        historico = self.historico(2)
        for distancia in (0, -7, 1, 49):
            historico[(FECHA - timedelta(days=distancia)).date()] = {"ida": dia(), "vuelta": dia()}
        self.assertIn("ida: histórico insuficiente", comparar_historico({"ida": dia(), "vuelta": []}, historico, FECHA))

    def test_cada_dia_pesa_igual_y_se_usan_los_cuatro_mas_recientes(self):
        historico = self.historico(6)
        historico[(FECHA - timedelta(weeks=1)).date()]["ida"] = dia(80) * 20
        resultado = comparar_historico({"ida": dia(), "vuelta": []}, historico, FECHA)
        self.assertIn("ida: similar frente a 4 lunes previos", resultado)


class IntegracionDiarioTests(unittest.TestCase):
    def test_resumen_real_cabe_en_mensaje_y_conserva_tres_rutas(self):
        datos = {ruta: diario.leer_log(info["log_file"], FECHA) for ruta, info in diario.RUTAS.items()}
        historico = {ruta: diario.leer_historico(info["log_file"], FECHA) for ruta, info in diario.RUTAS.items()}
        resultado = diario.construir_resumen(datos, FECHA, historico)
        self.assertIn("14 min menos de trayecto saliendo 30 min después", resultado)
        for info in diario.RUTAS.values():
            self.assertIn(info["nombre_destino"], resultado)
        self.assertLessEqual(len(resultado.encode("utf-16-le")) // 2, 4096)
        self.assertIn("no una previsión", resultado)

    def ejecutar_main(self, *argumentos):
        with patch("sys.argv", ["grafico_diario.py", "--fecha", "2026-09-07", *argumentos]), redirect_stdout(io.StringIO()):
            return diario.main()

    @patch.object(diario, "load_credentials", return_value=("test", "test"))
    @patch.object(diario, "construir_grafico", return_value=io.BytesIO(b"png"))
    @patch.object(diario, "requests")
    def test_no_telegram_no_hace_peticiones(self, requests, grafico, credenciales):
        self.assertEqual(self.ejecutar_main("--no-telegram"), 0)
        self.assertEqual(requests.mock_calls, [])

    @patch.object(diario, "load_credentials", return_value=("test", "test"))
    @patch.object(diario, "construir_grafico", return_value=io.BytesIO(b"png"))
    def test_fija_texto_y_solo_desfija_despues_de_publicar(self, grafico, credenciales):
        llamadas = Mock()
        with patch.object(diario, "enviar_foto", llamadas.foto), \
             patch.object(diario, "enviar_texto", llamadas.texto), \
             patch.object(diario, "desfijar_resumen_anterior", llamadas.desfijar), \
             patch.object(diario, "fijar_mensaje", llamadas.fijar):
            llamadas.texto.return_value = 42
            self.assertEqual(self.ejecutar_main(), 0)
            self.assertEqual([c[0] for c in llamadas.mock_calls], ["foto", "texto", "desfijar", "fijar"])
            llamadas.fijar.assert_called_once_with("test", "test", 42)
            llamadas.reset_mock()
            llamadas.texto.side_effect = RuntimeError("fallo de envío")
            with self.assertRaises(RuntimeError):
                self.ejecutar_main()
            llamadas.desfijar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
