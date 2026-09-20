#!/bin/bash

# Guardamos el nombre de este script para ignorarlo
SCRIPT_ACTUAL="$(basename "$0")"

# Guardamos la lista de archivos .sh en un arreglo de forma explícita
mapfile -t LISTA_SCRIPTS < <(ls *.sh 2>/dev/null)

for script in "${LISTA_SCRIPTS[@]}"; do
    # Verifica que el archivo exista y no sea el script principal
    if [ -f "$script" ] && [ "$script" != "$SCRIPT_ACTUAL" ]; then
        echo "Ejecutando: $script"
        bash "$script"
    fi
done

echo "Todos los scripts se ejecutaron correctamente uno por uno."