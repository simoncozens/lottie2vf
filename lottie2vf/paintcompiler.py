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


def string_to_var_scalar(s, font, f2dot14=False):
    converter = lambda x: float(x)
    if f2dot14:
        converter = lambda x: floatToFixed(float(x), 14)
    if not isinstance(s, str):
        s = "ANIM:0=" + str(s)
    v = VariableScalar()
    v.axes = font["fvar"].axes
    for location, value in re.findall(r"ANIM:([\d\.]+)=(\S+)", s):
        v.add_value({"ANIM": float(location)}, converter(value))
    if not (("ANIM", 0),) in v.values:
        first = re.match(r"ANIM:[\d\.]+=(\S+)", s)
        v.add_value({"ANIM": 0}, converter(first[1]))
    return v


def devariablize(val):
    if not isinstance(val, str):
        return val
    m = re.match(r"ANIM:[\d\.]+=(\S+)", val)
    if not m:
        raise ValueError(f"Bad variable value {val}")
    return float(m[1])


class PythonBuilder:
    def __init__(self, font) -> None:
        self.font = font
        self.palette = []
        self.variations = []
        self.deltaset = []
        self.varstorebuilder = OnlineVarStoreBuilder(["ANIM"])

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
        return { "Format": 12, "Paint": paint, "Transform": {
                "xx": matrix[0],
                "xy": matrix[1],
                "yx": matrix[2],
                "yy": matrix[3],
                "dx": matrix[4],
                "dy": matrix[5],
            }
        }

    def PaintTranslate(self, dx, dy, paint):
        return {"Format": 14, "dx": dx, "dy": dy, "Paint": paint}

    def PaintVarTranslate(self, dx, dy, paint):
        base = len(self.deltaset)

        vs = string_to_var_scalar(dx, self.font, f2dot14=False)
        dx_def, dx_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(dx_index)
        vs = string_to_var_scalar(dy, self.font, f2dot14=False)
        dy_def, dy_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(dy_index)

        return {
            "Format": 15,
            "dx": dx_def,
            "dy": dy_def,
            "Paint": paint,
            "VarIndexBase": base,
        }


    def PaintVarScale(self, scale_x, scale_y, paint):
        vs = string_to_var_scalar(scale_x, self.font, f2dot14=True)
        x_def, x_index = vs.add_to_variation_store(self.varstorebuilder)
        base = len(self.deltaset)
        self.deltaset.append(x_index)
        vs = string_to_var_scalar(scale_y, self.font, f2dot14=True)
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
        vs = string_to_var_scalar(scale_x, self.font, f2dot14=True)
        x_def, x_index = vs.add_to_variation_store(self.varstorebuilder)
        base = len(self.deltaset)
        self.deltaset.append(x_index)
        vs = string_to_var_scalar(scale_y, self.font, f2dot14=True)
        y_def, y_index = vs.add_to_variation_store(self.varstorebuilder)
        self.deltaset.append(y_index)
        _, cx_ix = string_to_var_scalar(0, self.font).add_to_variation_store(
            self.varstorebuilder
        )
        _, cy_ix = string_to_var_scalar(0, self.font).add_to_variation_store(
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

    def PaintRotateAroundCenter(self, angle, center, paint):
        return {
            "Format": 26,
            "angle": angle,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
        }

    def PaintVarRotateAroundCenter(self, angle, center, paint):
        vs = string_to_var_scalar(angle, self.font, f2dot14=True)
        angle_def, angle_index = vs.add_to_variation_store(self.varstorebuilder)
        base = len(self.deltaset)

        _, cx_ix = string_to_var_scalar(0, self.font).add_to_variation_store(
            self.varstorebuilder
        )
        _, cy_ix = string_to_var_scalar(0, self.font).add_to_variation_store(
            self.varstorebuilder
        )
        self.deltaset.append(cx_ix)
        self.deltaset.append(cy_ix)

        return {
            "Format": 27,
            "angle": angle_def,
            "centerX": center[0],
            "centerY": center[1],
            "Paint": paint,
            "VarIndexBase": base,
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
    exec(python_code, globals(), this_locals)

    builder.build_colr(this_locals["glyphs"])
    builder.build_palette()
