from .lottieparser import LottieParser, load_animation
from .paintcompiler import compile_paints
from .font import font_builder, add_glyphs
from pathlib import Path
import sys
import argparse

parser = argparse.ArgumentParser(description='Convert a .lottie file to a variable font')
parser.add_argument('--verbose', '-v', action='store_true',
                    help='display the generated paint description')
parser.add_argument('--output', '-o', dest='output',
                    help='output TTF file')
parser.add_argument('input', metavar='JSON',
                    help='input lottie file')

args = parser.parse_args()


infile = Path(args.input)
if not args.output:
 args.output = infile.with_suffix(".ttf")

an = load_animation(infile)

paint_builder = LottieParser(an)

# Create the paint description and the glyph descriptions
paint_builder.process()
python_description = 'glyphs["baseglyph"] = ' + paint_builder.paint

# Display the glyph description
if args.verbose:
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

print(f"Written on {args.output}")
fontbuilder.font.save(args.output)

