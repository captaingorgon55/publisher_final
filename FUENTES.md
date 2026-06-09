# Guía de Fuentes Personalizadas

## Problema solucionado
Las letras cambiaban de tamaño al publicar porque el código buscaba fuentes del sistema que:
- No existían en todos los equipos
- Renderizaban diferente según el SO
- Fallaban al fallback (letra pequeña/fea)

## Solución: Fuentes en el proyecto

Ahora puedes incluir una fuente TTF personalizada en la carpeta `assets/fonts/` y se usará **siempre**, garantizando consistencia.

## ¿Cómo usar Abril Titling?

### Opción 1: Copiar el archivo TTF (Recomendado)
1. Coloca tu archivo `AbrilTitling-Regular.ttf` (o similar) en:
   ```
   assets/fonts/
   ```

2. La fuente se detectará automáticamente y se usará en todas las tarjetas

3. Ejemplo de uso:
   ```python
   from generator import generate_card_from_image
   from PIL import Image
   
   # La fuente se busca automáticamente en assets/fonts/
   img = Image.open("foto.jpg")
   tarjeta = generate_card_from_image(
       img,
       section="Política",
       title="Mi titular",
       template="classic"
   )
   tarjeta.save("output.png")
   ```

### Opción 2: Especificar la ruta manualmente
```python
tarjeta = generate_card_from_image(
    img,
    section="Política",
    title="Mi titular",
    template="classic",
    font_path="C:/ruta/a/AbrilTitling-Regular.ttf"  # Ruta personalizada
)
```

## ¿Qué archivos TTF puedo usar?

Cualquier archivo `.ttf` válido, por ejemplo:
- `AbrilTitling-Regular.ttf` (serif elegante)
- `ArialBD.ttf` (sans-serif)
- `Georgia.ttf` (serif clásica)
- Cualquier otra fuente TrueType

## Ubicación de la carpeta

```
ee-publisher_v2/
├── assets/
│   ├── fonts/          ← Aquí va tu TTF
│   │   └── AbrilTitling-Regular.ttf
│   ├── fondos/
│   ├── graficos/
│   ├── logos/
│   ├── secciones/
│   └── secciones-icono/
├── generator.py
├── app.py
└── README.md
```

## Cómo el código carga fuentes

1. **Primero:** Busca en `assets/fonts/` cualquier `.ttf` disponible
2. **Si encuentras:** La usa (consistencia garantizada)
3. **Si no:** Intenta cargar del sistema (Georgia, Arial, etc.)
4. **Si nada funciona:** Usa fuente por defecto (muy fea, evitar)

## Archivos TTF disponibles en Windows 10/11

Si necesitas probar sin Abril Titling, estos existen en Windows:
- `C:\Windows\Fonts\georgia.ttf` (serif elegante)
- `C:\Windows\Fonts\arial.ttf` (sans-serif limpia)
- `C:\Windows\Fonts\calibri.ttf` (moderna)

## ¿Dónde obtener fuentes?

- **Google Fonts** (gratis): https://fonts.google.com/
- **DaFont** (variadas): https://www.dafont.com/
- **Font Squirrel** (libre): https://www.fontsquirrel.com/

Busca "Abril Titling" en Google Fonts si quieres la misma que mencionaste.

## Verificar que funciona

```python
from generator import list_fondos, FONTS_DIR
import os

# Ver fuentes disponibles en el proyecto
print("Fuentes en assets/fonts/:")
if os.path.exists(FONTS_DIR):
    for f in os.listdir(FONTS_DIR):
        print(f"  - {f}")
else:
    print("  (carpeta no existe)")
```

## Parámetros de control de tamaño

También puedes ajustar el tamaño con estos parámetros:

```python
tarjeta = generate_card_from_image(
    img,
    section="Política",
    title="Mi titular más largo que quiero más pequeño",
    template="classic",
    # El código automáticamente ajusta el tamaño si el texto no cabe
    # Estos son los parámetros internos (no necesitas cambiarlos):
    # - size_start: tamaño inicial (58px)
    # - size_min: mínimo permitido (36px)
    # - max_lines: máximo de líneas
)
```

## Resolución de problemas

### Las letras siguen cambiando
- Verifica que el archivo `.ttf` esté en `assets/fonts/`
- Confirma que el archivo no está corrupto (abrelo en un editor de fuentes)

### El archivo TTF es muy grande
- Usa compresores de fuentes online (ej: Font Squirrel WebFont Generator)
- O simplemente usa una fuente del sistema en su lugar

### Necesito varias fuentes
- Coloca múltiples `.ttf` en `assets/fonts/`
- El código usará el primero que encuentre
- Para cambiar cual, usa el parámetro `font_path` manualmente
