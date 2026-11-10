"""
Líneas de colectivo cuyo recorrido está íntegramente dentro de CABA.

Criterio: la columna **Administración = GCBA** del listado de Wikipedia
(`proyectoconsola/informacion de wikipedia.txt`). La jurisdicción es el proxy
exacto de lo que buscamos: una línea la administra el GCBA sólo si no sale de
la Ciudad; apenas cruza la General Paz o el Riachuelo pasa a jurisdicción
nacional. Las líneas 200+ del listado son provinciales (PBA) y no tienen
columna de administración.

Ojo con parsear el TXT a mano: "Nación" también aparece dentro de
"Congreso de la Nación Argentina" en la columna de recorrido, así que un
`"Nación" in fila` clasifica mal a la 12 y la 50. Hay que leer el campo
posicionalmente.
"""

# 27 líneas. Verificado contra LABEL_LINE_MAP.json: todas tienen sufijo asignado.
LINEAS_CABA: tuple[str, ...] = (
    "4", "7", "12", "25", "26", "34", "39", "42", "44", "47",
    "50", "61", "62", "64", "65", "68", "76", "84", "102", "106",
    "107", "108", "109", "115", "118", "132", "151",
)

# De esas, las que tienen recorrido en line_shapes.json. Sirven como conjunto
# de validación: ahí se puede contrastar el método sin recorrido contra la
# proyección geométrica.
CABA_CON_SHAPE: tuple[str, ...] = ("26", "39", "42", "151")

if __name__ == "__main__":
    print(" ".join(LINEAS_CABA))
