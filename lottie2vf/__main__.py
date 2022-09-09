from .lottieparser import LottieParser, load_animation
from .paintcompiler import compile_paints
from .font import font_builder, add_glyphs
from pathlib import Path
import sys

infile = Path(sys.argv[1])
outfile = infile.with_suffix(".ttf")

an = load_animation(infile)

paint_builder = LottieParser(an)

# Create the paint description and the glyph descriptions
paint_builder.process()
python_description = 'glyphs["baseglyph"] = ' + paint_builder.paint

try:
    from black import format_file_contents, Mode
    python_description = format_file_contents(python_description, fast=True, mode=Mode(line_length=78))
except:
    pass

print(python_description)

# Add the glyph descriptions to the font
fontbuilder = font_builder(an)
add_glyphs(fontbuilder, paint_builder.glyphs)

# Compile COLR/CPAL tables
compile_paints(fontbuilder.font, python_description)

print(f"Written on {outfile}")
fontbuilder.font.save(outfile)

