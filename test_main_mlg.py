import unittest
from unittest.mock import Mock, patch

import requests

from main_mlg import TraficoChecker, comprobar_rutas_agrupadas


class TraficoTests(unittest.TestCase):
    def setUp(self):
        credentials = patch.object(TraficoChecker, "load_credentials", return_value=("test", "test"))
        api_key = patch.object(TraficoChecker, "load_api_key", return_value="test")
        credentials.start()
        api_key.start()
        self.addCleanup(credentials.stop)
        self.addCleanup(api_key.stop)

    @patch("main_mlg.time.sleep")
    @patch("main_mlg.requests.get")
    def test_recupera_timeout_y_error_temporal(self, get, sleep):
        unavailable = requests.HTTPError(response=Mock(status_code=503))
        response = Mock()
        response.json.return_value = {"routes": [{"summary": {"travelTimeInSeconds": 2700}}]}
        get.side_effect = [requests.Timeout(), unavailable, response]
        self.assertEqual(TraficoChecker().obtener_duracion(), (45, False))
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("main_mlg.time.sleep")
    @patch("main_mlg.requests.get")
    def test_limita_reintentos(self, get, sleep):
        get.side_effect = requests.Timeout()
        with self.assertRaises(requests.Timeout):
            TraficoChecker().obtener_duracion()
        self.assertEqual(get.call_count, 3)

    @patch("main_mlg.time.sleep")
    @patch("main_mlg.requests.get")
    def test_no_reintenta_error_permanente(self, get, sleep):
        get.side_effect = requests.HTTPError(response=Mock(status_code=401))
        with self.assertRaises(requests.HTTPError):
            TraficoChecker().obtener_duracion()
        self.assertEqual(get.call_count, 1)
        sleep.assert_not_called()

    @patch.object(TraficoChecker, "send_telegram")
    def test_mantiene_ambos_sentidos_si_falla_cualquier_trayecto(self, send):
        for ruta in TraficoChecker.RUTAS:
            for sentido in ("ida", "vuelta"):
                with self.subTest(ruta=ruta, sentido=sentido):
                    def run(checker, enviar_telegram=True):
                        self.assertFalse(enviar_telegram)
                        if (checker.ruta, checker.sentido) == (ruta, sentido):
                            raise requests.Timeout()
                        return checker.sentido_str + "\n✅ Tráfico muy fluido (20 min)"

                    with patch.object(TraficoChecker, "run", autospec=True, side_effect=run):
                        mensaje = comprobar_rutas_agrupadas()
                    self.assertEqual(mensaje.count("Datos no disponibles"), 1)
                    for info in TraficoChecker.RUTAS.values():
                        for origen, destino in ((info['nombre_origen'], info['nombre_destino']),
                                                (info['nombre_destino'], info['nombre_origen'])):
                            self.assertIn(f"{origen} → {destino}\n", mensaje)
                    send.assert_called_with(mensaje)

    @patch.object(TraficoChecker, "send_telegram")
    @patch.object(TraficoChecker, "run", side_effect=requests.Timeout())
    def test_informa_si_fallan_todos(self, run, send):
        mensaje = comprobar_rutas_agrupadas()
        self.assertEqual(mensaje.count("Datos no disponibles"), 6)
        send.assert_called_once_with(mensaje)


if __name__ == "__main__":
    unittest.main()
