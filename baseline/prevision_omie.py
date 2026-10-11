"""¿Supera el machine learning a las reglas obvias al prever el precio de la luz a 2-7 días?

Uso: python -I prevision_omie.py <carpeta_omie> <carpeta_meteo>
- carpeta_omie: un fichero AAAAMMDD.txt por día (marginalpdbc de OMIE; 6ª columna = España).
  Desde octubre de 2025 el mercado es cuartohorario (96 periodos): se promedia a horas.
- carpeta_meteo: JSON de la Previous Runs API de Open-Meteo por punto, con
  wind_speed_100m / shortwave_radiation / temperature_2m _previous_dayK (K = días de antelación).

Escenario realista: el día D por la tarde ya se conoce el precio de D+1 (OMIE lo publica hacia las 13:00).
Se prevé cada hora de T = D+k, k = 2..7, usando solo precios hasta D+1 y la previsión
meteorológica emitida k días antes de T (previous_dayK).
Entrenamiento: hasta el 30-09-2025. Prueba: 01-10-2025 en adelante, reentrenando cada mes (la red neuronal, cada 3 meses) con ventana creciente.
"""
import sys, os, glob, json, datetime as dt, time
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

OMIE, METEO = sys.argv[1], sys.argv[2]
KS = range(2, 8)
INICIO_PRUEBA = dt.date(2025, 10, 1)
FESTIVOS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}  # nacionales fijos

# ---------- precios ----------
precio = {}
for f in sorted(glob.glob(os.path.join(OMIE, '*.txt'))):
    filas = []
    for linea in open(f, encoding='latin-1'):
        p = linea.strip().split(';')
        if len(p) >= 6 and p[0].isdigit():
            filas.append((int(p[3]), float(p[5])))
    if not filas:
        continue
    n = len(filas); paso = 4 if n >= 90 else 1
    horas = [[] for _ in range(24)]
    for per, v in filas:
        horas[min((per - 1) // paso, 23)].append(v)
    if all(horas):
        d = dt.datetime.strptime(os.path.basename(f)[:8], '%Y%m%d').date()
        precio[d] = np.array([np.mean(h) for h in horas])
dias = sorted(precio)
print(f'días con precio: {len(dias)} ({dias[0]} a {dias[-1]})')

# ---------- meteorología ----------
meteo = {}  # (punto, var, k) -> {(fecha, hora): valor}
for f in glob.glob(os.path.join(METEO, '*.json')):
    pto = os.path.basename(f)[:-5]
    h = json.load(open(f))['hourly']
    tiempos = [dt.datetime.fromisoformat(t) for t in h['time']]
    for var in ('wind_speed_100m', 'shortwave_radiation', 'temperature_2m'):
        for k in KS:
            vals = h[f'{var}_previous_day{k}']
            meteo[(pto, var, k)] = {(t.date(), t.hour): v for t, v in zip(tiempos, vals) if v is not None}
VIENTO = [p for p in ('zaragoza', 'burgos', 'lugo', 'albacete') if (p, 'wind_speed_100m', 2) in meteo]
SOL = [p for p in ('sevilla', 'badajoz', 'albacete') if (p, 'shortwave_radiation', 2) in meteo]
print('puntos de viento:', VIENTO, '| de sol:', SOL)

def met(var, pts, T, hora, k):
    if not pts or any((p, var, k) not in meteo for p in pts):
        return None
    vals = [meteo[(p, var, k)].get((T, hora)) for p in pts]
    return None if any(v is None for v in vals) else float(np.mean(vals))

# ---------- construir ejemplos ----------
X, Xm, Y, info = [], [], [], []  # Xm: con meteorología
dset = set(dias)
for D in dias:
    D1 = D + dt.timedelta(days=1)
    hist = [D1 - dt.timedelta(days=i) for i in range(14)]
    if not all(d in dset for d in hist):
        continue
    ultimo = precio[D1]; media7 = np.mean([precio[d] for d in hist[:7]], axis=0)
    nivel7 = float(np.mean(media7)); nivel1 = float(ultimo.mean())
    for k in KS:
        T = D + dt.timedelta(days=k)
        if T not in dset:
            continue
        semana = T - dt.timedelta(days=7)
        if semana > D1:
            semana = T - dt.timedelta(days=14)
        vt_dia = [met('wind_speed_100m', VIENTO, T, hh, k) for hh in range(24)]
        sol_dia = [met('shortwave_radiation', SOL, T, hh, k) for hh in range(24)]
        hay_met = all(v is not None for v in vt_dia + sol_dia)
        for hh in range(24):
            base = [hh, T.weekday(), T.month, int((T.month, T.day) in FESTIVOS or T.weekday() == 6), k,
                    ultimo[hh], media7[hh], precio[semana][hh], nivel1, nivel7,
                    float(ultimo.max() - ultimo.min())]
            if hay_met:
                temp = met('temperature_2m', ['madrid'], T, hh, k)
                extra = [vt_dia[hh], float(np.mean(vt_dia)), sol_dia[hh], float(np.sum(sol_dia)),
                         temp if temp is not None else np.nan]
            else:
                extra = [np.nan] * 5
            X.append(base); Xm.append(base + extra); Y.append(precio[T][hh])
            info.append((D, T, k, hh, hay_met, ultimo[hh], precio[semana][hh], media7[hh]))
X, Xm, Y = np.array(X), np.array(Xm, dtype=float), np.array(Y)
D_arr = np.array([i[0] for i in info]); T_arr = np.array([i[1] for i in info])
K_arr = np.array([i[2] for i in info]); H_arr = np.array([i[3] for i in info])
MET = np.array([i[4] for i in info])
print(f'ejemplos: {len(Y)} | con meteorología: {MET.sum()}')

# Solo periodo con meteorología, para comparar todo sobre las mismas filas
usa = MET
prueba = usa & (T_arr >= INICIO_PRUEBA) & (D_arr >= INICIO_PRUEBA - dt.timedelta(days=1))
print(f'filas de prueba: {prueba.sum()} ({min(T_arr[prueba])} a {max(T_arr[prueba])})')

pred = {}
pred['Regla: repetir mañana (D+1)'] = np.array([i[5] for i in info])
pred['Regla: misma hora, semana pasada'] = np.array([i[6] for i in info])
pred['Regla: media de los últimos 7 días'] = np.array([i[7] for i in info])

def walk_forward(nombre, crear, Xf, escalar=False, cada=1):
    out = np.full(len(Y), np.nan); t0 = time.time()
    meses = sorted({(t.year, t.month) for t in T_arr[prueba]})
    n_fit = 0
    for i, (a, m) in enumerate(meses):
        ini = dt.date(a, m, 1)
        te = prueba & np.array([t.year == a and t.month == m for t in T_arr])
        Xte = np.nan_to_num(Xf[te]) if escalar else Xf[te]
        if i % cada == 0:
            tr = usa & (T_arr < ini) & (D_arr < ini - dt.timedelta(days=1))
            Xtr = Xf[tr]
            sc = None
            if escalar:
                Xtr = np.nan_to_num(Xtr); sc = StandardScaler().fit(Xtr); Xtr = sc.transform(Xtr)
            mod = crear().fit(Xtr, Y[tr]); n_fit += 1
        out[te] = mod.predict(sc.transform(Xte) if sc is not None else Xte)
    pred[nombre] = out
    print(f'  {nombre}: entrenado {n_fit} veces en {time.time()-t0:.0f} s', flush=True)

print('\nEntrenando (reentreno mensual)...')
walk_forward('ML: gradient boosting sin meteorología', lambda: HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=0), X)
walk_forward('ML: gradient boosting con meteorología', lambda: HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=0), Xm)
walk_forward('Red neuronal (MLP 64-64) con meteorología', lambda: MLPRegressor(hidden_layer_sizes=(64, 64), batch_size=1024, max_iter=60, early_stopping=True, random_state=0), Xm, escalar=True, cada=3)

# ---------- métricas ----------
y = Y[prueba]
print(f'\nPrecio medio en la prueba: {y.mean():.1f} €/MWh (desviación típica {y.std():.1f})')
print(f"\n{'Modelo':<44}{'MAE':>7}" + ''.join(f'{"D+"+str(k):>7}' for k in KS))
for n, p in pred.items():
    e = np.abs(p[prueba] - y)
    print(f'{n:<44}{e.mean():>7.1f}' + ''.join(f'{e[K_arr[prueba]==k].mean():>7.1f}' for k in KS))

# Decisión práctica 1: ventana de 4 horas seguidas más barata de cada día (cargar el coche)
def ventana(v):
    s = [v[i:i+4].mean() for i in range(21)]; return int(np.argmin(s))
print('\nDecisión 1: elegir las 4 horas seguidas más baratas del día T (sobrecoste frente a la mejor ventana real, €/MWh)')
claves = sorted({(d, t) for d, t, m in zip(D_arr[prueba], T_arr[prueba], prueba[prueba])})
grupos = {}
for idx in np.where(prueba)[0]:
    grupos.setdefault((D_arr[idx], T_arr[idx]), []).append(idx)
reglas_fijas = {'Regla fija: siempre 13-17 h': 13, 'Regla fija: siempre 2-6 h': 2}
res = {n: [] for n in list(pred) + list(reglas_fijas)}
for g, idxs in grupos.items():
    if len(idxs) != 24: continue
    idxs = sorted(idxs, key=lambda i: H_arr[i]); real = Y[idxs]
    mejor = min(real[i:i+4].mean() for i in range(21))
    for n, p in pred.items():
        w = ventana(p[idxs]); res[n].append(real[w:w+4].mean() - mejor)
    for n, h0 in reglas_fijas.items():
        res[n].append(real[h0:h0+4].mean() - mejor)
for n, v in sorted(res.items(), key=lambda kv: np.mean(kv[1])):
    print(f'  {n:<44} {np.mean(v):6.1f}   (n={len(v)})')

# Decisión práctica 2: qué día de D+2..D+7 es el más barato (p. ej. para una carga grande)
print('\nDecisión 2: elegir el día más barato de D+2..D+7 por precio medio (sobrecoste frente al día más barato real, €/MWh)')
pordia = {}
for idx in np.where(prueba)[0]:
    pordia.setdefault(D_arr[idx], {}).setdefault(T_arr[idx], []).append(idx)
res2 = {n: [] for n in list(pred) + ['Regla fija: el domingo (o el más próximo)']}
for D, ts in pordia.items():
    ts = {t: ix for t, ix in ts.items() if len(ix) == 24}
    if len(ts) != 6: continue
    reales = {t: Y[ix].mean() for t, ix in ts.items()}; mejor = min(reales.values())
    for n, p in pred.items():
        t_el = min(ts, key=lambda t: p[ts[t]].mean()); res2[n].append(reales[t_el] - mejor)
    dom = [t for t in ts if t.weekday() == 6]
    t_el = dom[0] if dom else min(ts, key=lambda t: abs(6 - t.weekday()))
    res2['Regla fija: el domingo (o el más próximo)'].append(reales[t_el] - mejor)
for n, v in sorted(res2.items(), key=lambda kv: np.mean(kv[1])):
    print(f'  {n:<44} {np.mean(v):6.1f}   (n={len(v)})')

# ---------- intervalos de confianza (bootstrap por días de emisión, 1.000 remuestreos) ----------
def ic(dif, n=1000):
    dif = np.array(dif); rng = np.random.default_rng(1)
    b = np.sort([dif[rng.integers(0, len(dif), len(dif))].mean() for _ in range(n)])
    return dif.mean(), b[25], b[975]
print('\nIntervalos de confianza al 95 % (negativo = el modelo es mejor que la regla)')
emis = sorted({d for d in D_arr[prueba]})
err = {n: np.abs(p - Y) for n, p in pred.items()}
def por_dia(n):
    return [err[n][prueba & (D_arr == d)].mean() for d in emis]
for a, b in (('ML: gradient boosting con meteorología', 'Regla: media de los últimos 7 días'),
             ('Red neuronal (MLP 64-64) con meteorología', 'Regla: media de los últimos 7 días'),
             ('ML: gradient boosting sin meteorología', 'Regla: media de los últimos 7 días')):
    m, lo, hi = ic(np.array(por_dia(a)) - np.array(por_dia(b)))
    print(f'  MAE {a} - {b}: {m:+.1f} [{lo:+.1f}, {hi:+.1f}] €/MWh')
for a, b in (('ML: gradient boosting con meteorología', 'Regla fija: siempre 13-17 h'),):
    m, lo, hi = ic(np.array(res[a]) - np.array(res[b]))
    print(f'  Decisión 1, {a} - {b}: {m:+.1f} [{lo:+.1f}, {hi:+.1f}] €/MWh')
for a in ('Red neuronal (MLP 64-64) con meteorología', 'ML: gradient boosting con meteorología'):
    m, lo, hi = ic(np.array(res2[a]) - np.array(res2['Regla fija: el domingo (o el más próximo)']))
    print(f'  Decisión 2, {a} - domingo: {m:+.1f} [{lo:+.1f}, {hi:+.1f}] €/MWh')
