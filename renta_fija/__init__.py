"""Renta fija: todo lo propio de bonos y letras.

    renta_fija/
    ├── fichas/          datos de cada bono según su norma de emisión (*.toml) y los PDF en prospectos/
    ├── calculadoras/    cuentas puras, sin internet ni archivos:
    │   ├── motor.py     TIR, duration, convexidad, valor técnico, paridad (común a todas las familias)
    │   └── cer.py       cómo se arman los flujos de los bonos CER (después: tasa fija, hard dollar...)
    └── leer_fichas.py   lee y valida las fichas

La herramienta que usa el agente está en tools/bonos.py; los precios y el CER llegan por conexiones/.
"""
