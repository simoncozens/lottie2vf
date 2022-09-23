from fontTools.ttLib import TTFont
import argparse
from datadiff import diff
from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.varLib.varStore import OnlineVarStoreBuilder
from fontTools.varLib.builder import buildDeltaSetIndexMap
from fontTools.feaLib.variableScalar import VariableScalar
from fontTools.misc.fixedTools import floatToFixed, fixedToFloat
from fontTools.ttLib.tables._f_v_a_r import Axis
import re


def compile_color(c):
    return tuple(int(x, 16) / 255 for x in [c[1:3], c[3:5], c[5:7], c[7:9]])


def compile_colors(colors):
    return [compile_color(c) for c in colors]


class PythonBuilder:
    def __init__(self, font) -> None:
        self.font = font
        self.palette = []
        self.variations = []
        self.deltaset = []
        assert "fvar" in font, "Font needs an fvar table"
        self.axes = font["fvar"].axes
        axis_tags = [x.axisTag for x in self.axes]
        self.varstorebuilder = OnlineVarStoreBuilder(axis_tags)

    def string_to_var_scalar(self, s, f2dot14=False, converter=None):
        if converter is None:
            converter = lambda x: float(x)
            if f2dot14:
                converter = lambda x: floatToFixed(float(x), 14)
        v = VariableScalar()
        v.axes = self.axes
        default_location = {axis.axisTag: axis.defaultValue for axis in self.axes}
        if not isinstance(s, str):
            v.add_value(default_location, converter(float(s)))
            return v

        first_value = None

        for values in s.split():
            locations, value = values.split(":")
            if converter(value) <= -32768 or converter(value) >= 32768:
                raise ValueError(f"Value too big in '{s}'")
            location = {}
            for loc in locations.split(","):
                axis, axis_loc = loc.split("=")
                location[axis] = float(axis_loc)
            v.add_value(location, converter(value))

            if first_value is None:
                first_value = value

        if not tuple(default_location.items()) in v.values:
            if first_value is None:
                raise ValueError(f"No default value OR first value in '{s}'")
            v.add_value(default_location, converter(first_value))
        return v

    def get_palette_index(self, color):
        if not isinstance(color, list):
            color = [color]
        if color not in self.palette:
            self.palette.append(color)
        return self.palette.index(color)

    def PaintColrLayers(self, layers):
        return {"Format": 1, "Layers": layers}

    def PaintLinearGradient(self, pt0, pt1, pt2, colorline):
        return {
            "Format": 4,
            "x0": pt0[0],
            "y0": pt0[1],
            "x1": pt1[0],
            "y1": pt1[1],
            "x2": pt2[0],
            "y2": pt2[1],
            "ColorLine": colorline,
        }

    def PaintSolid(self, col_or_colrs, alpha=1.0):
        return {
            "Format": 2,
            "PaletteIndex": self.get_palette_index(col_or_colrs),
            "Alpha": alpha,
        }

    def PaintVarSolid(self, col_or_colrs, alpha):
        base = len(self.deltaset)
        vs = self.string_to_var_scalar(alpha, f2dot14=True)
        alpha_def, alpha_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(alpha_index)
        return {
            "Format": 3,
            "PaletteIndex": self.get_palette_index(col_or_colrs),
            "Alpha": fixedToFloat(alpha_def, 14),
            "VarIndexBase": base,
        }

    def PaintSweepGradient(self, pt, startAngle, endAngle, colorline):
        return {
            "Format": 8,
            "centerX": pt[0],
            "centerY": pt[1],
            "startAngle": startAngle,
            "endAngle": endAngle,
            "ColorLine": colorline,
        }

    def PaintGlyph(self, glyph, paint=None):
        return {"Format": 10, "Glyph": glyph, "Paint": paint}

    def PaintTransform(self, matrix, paint):
        return {
            "Format": 12,
            "Paint": paint,
            "Transform": {
                "xx": matrix[0],
                "xy": matrix[1],
                "yx": matrix[2],
                "yy": matrix[3],
                "dx": matrix[4],
                "dy": matrix[5],
            },
        }

    def PaintTranslate(self, dx, dy, paint):
        return {"Format": 14, "dx": dx, "dy": dy, "Paint": paint}

    def PaintVarTranslate(self, dx, dy, paint):
        base = len(self.deltaset)

        vs = self.string_to_var_scalar(dx, f2dot14=False)
        dx_default, dx_index = vs.add_to_variation_store(self.varstorebuilder)
        vs = self.string_to_var_scalar(dy, f2dot14=False)
        dy_default, dy_index = vs.add_to_variation_store(self.varstorebuilder)

        self.deltaset.append(dx_index)
        self.deltaset.append(dy_index)

        return {
            "Format": 15,
            "dx": dx_default,
            "dy": dy_default,
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintScale(self, scale_x, scale_y, paint):
        return {
            "Format": 16,
            "scaleX": scale_x,
            "scaleY": scale_y,
            "Paint": paint,
        }

    def PaintVarScale(self, scale_x, scale_y, paint):
        vs = self.string_to_var_scalar(scale_x, f2dot14=True)
        x_def, x_index = vs.add_to_variation_store(self.varstorebuilder)
        base = len(self.deltaset)
        self.deltaset.append(x_index)
        vs = self.string_to_var_scalar(scale_y, f2dot14=True)
        y_def, y_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(y_index)
        return {
            "Format": 17,
            "scaleX": fixedToFloat(x_def, 14),
            "scaleY": fixedToFloat(y_def, 14),
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintScaleAroundCenter(self, scale_x, scale_y, center, paint):
        return {
            "Format": 18,
            "scaleX": scale_x,
            "scaleY": scale_y,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
        }

    def PaintVarScaleAroundCenter(self, scale_x, scale_y, center, paint):
        vs = self.string_to_var_scalar(scale_x, f2dot14=True)
        x_def, x_index = vs.add_to_variation_store(self.varstorebuilder)
        base = len(self.deltaset)
        self.deltaset.append(x_index)
        vs = self.string_to_var_scalar(scale_y, f2dot14=True)
        y_def, y_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(y_index)
        _, cx_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        _, cy_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        self.deltaset.append(cx_ix)
        self.deltaset.append(cy_ix)

        return {
            "Format": 19,
            "scaleX": fixedToFloat(x_def, 14),
            "scaleY": fixedToFloat(y_def, 14),
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintRotate(self, angle, paint):
        return {"Format": 24, "angle": angle, "Paint": paint}

    def PaintVarRotate(self, angle, paint):
        base = len(self.deltaset)

        vs = self.string_to_var_scalar(
            angle, converter=lambda x: floatToFixed(float(x) / 180, 14)
        )
        angle_def, angle_index = vs.add_to_variation_store(self.varstorebuilder)

        return {
            "Format": 25,
            "angle": fixedToFloat(angle_def, 14) * 180,
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintRotateAroundCenter(self, angle, center, paint):
        return {
            "Format": 26,
            "angle": angle,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
        }

    def PaintVarRotateAroundCenter(self, angle, center, paint):
        base = len(self.deltaset)

        vs = self.string_to_var_scalar(
            angle, converter=lambda x: floatToFixed(float(x) / 180, 14)
        )
        angle_def, angle_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(angle_index)

        _, cx_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        _, cy_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        self.deltaset.append(cx_ix)
        self.deltaset.append(cy_ix)

        return {
            "Format": 27,
            "angle": fixedToFloat(angle_def, 14) * 180,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintVarSkewAroundCenter(self, angle_x, angle_y, center, paint):
        base = len(self.deltaset)

        vs = self.string_to_var_scalar(
            angle_x, f2dot14=True, converter=lambda x: floatToFixed(float(x) / 180, 14)
        )
        angle_x_def, angle_x_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(angle_x_index)

        vs = self.string_to_var_scalar(
            angle_y, f2dot14=True, converter=lambda x: floatToFixed(float(x) / 180, 14)
        )
        angle_y_def, angle_y_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(angle_y_index)

        _, cx_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        _, cy_ix = self.string_to_var_scalar(0).add_to_variation_store(
            self.varstorebuilder
        )
        self.deltaset.append(cx_ix)
        self.deltaset.append(cy_ix)

        return {
            "Format": 31,
            "xSkewAngle": fixedToFloat(angle_x_def, 14) * 180,
            "ySkewAngle": fixedToFloat(angle_y_def, 14) * 180,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
            "VarIndexBase": base,
        }

    def PaintComposite(self, mode, src, dst):
        return {
            "Format": 32,
            "CompositeMode": mode,
            "SourcePaint": src,
            "BackdropPaint": dst,
        }

    def ColorLine(self, start_or_stops, end=None, extend="pad"):
        if end is None:
            stops = start_or_stops
        else:
            stops = {0.0: start_or_stops, 1.0: end}
        colorstop = []
        for k, v in stops.items():
            colorstop.append(
                {
                    "StopOffset": k,
                    "Alpha": 1.0,
                    "PaletteIndex": self.get_palette_index(v),
                }
            )
        return {"ColorStop": colorstop, "Extend": extend}

    def build_palette(self):
        palette = [compile_colors(stop) for stop in self.palette]
        t_palette = list(map(list, zip(*palette)))
        self.font["CPAL"] = buildCPAL(t_palette)

    def build_colr(self, glyphs):
        store = self.varstorebuilder.finish()
        mapping = store.optimize()
        self.deltaset = [mapping[v] for v in self.deltaset]
        self.font["COLR"] = buildCOLR(
            glyphs,
            varStore=store,
            varIndexMap=buildDeltaSetIndexMap(self.deltaset),
            version=1,
        )


def compile_paints(font, python_code):
    builder = PythonBuilder(font)
    methods = [
        x for x in dir(builder) if x.startswith("Paint") or x.startswith("ColorLine")
    ]
    this_locals = {"glyphs": {}}
    for method in methods:
        this_locals[method] = getattr(builder, method)
    exec(python_code, this_locals, this_locals)

    builder.build_colr(this_locals["glyphs"])
    builder.build_palette()
