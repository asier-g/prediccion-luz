"""Descarga los datos del experimento en una carpeta: precios de OMIE (2023 a hoy) y previsiones pasadas de Open-Meteo.
Uso: python descarga_datos.py <carpeta_destino>   -> crea <carpeta>/omie y <carpeta>/meteo
Tarda unos 15-25 minutos (Open-Meteo responde lento a peticiones de varios años)."""
import urllib.request, datetime, time, os, sys
from concurrent.futures import ThreadPoolExecutor
S = sys.argv[1]; FIN = datetime.date.today()
os.makedirs(os.path.join(S, 'omie'), exist_ok=True); os.makedirs(os.path.join(S, 'meteo'), exist_ok=True)
puntos = {'zaragoza': (41.65, -0.88), 'burgos': (42.34, -3.70), 'lugo': (43.01, -7.56), 'albacete': (38.99, -1.86),
          'sevilla': (37.39, -5.98), 'badajoz': (38.88, -6.97), 'madrid': (40.42, -3.70)}
vars_ = ','.join(f'{v}_previous_day{k}' for v in ('wind_speed_100m', 'shortwave_radiation', 'temperature_2m') for k in range(1, 8))
for n, (la, lo) in puntos.items():
    out = os.path.join(S, 'meteo', n + '.json')
    if os.path.exists(out): continue
    url = (f'https://previous-runs-api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}&hourly={vars_}'
           f'&start_date=2023-01-01&end_date={FIN}&timezone=Europe%2FMadrid')
    with urllib.request.urlopen(url, timeout=600) as r: open(out, 'wb').write(r.read())
    print('meteo', n, flush=True); time.sleep(2)
def baja(d):
    f = os.path.join(S, 'omie', d.strftime('%Y%m%d') + '.txt')
    if os.path.exists(f) and os.path.getsize(f) > 100: return
    url = f"https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_{d.strftime('%Y%m%d')}.1"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: open(f, 'wb').write(r.read()); return
        except Exception: time.sleep(5)
fechas = [datetime.date(2023, 1, 1) + datetime.timedelta(days=i) for i in range((FIN - datetime.date(2023, 1, 1)).days + 1)]
with ThreadPoolExecutor(4) as ex: list(ex.map(baja, fechas))
print('listo', flush=True)
