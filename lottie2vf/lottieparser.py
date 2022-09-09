from lottie.utils import restructure
from lottie.nvector import NVector
from lottie import objects
import json
import sys
import logging
from babelfont import Layer
import math

from .transformation import apply_transform_to_paint

logger = logging.getLogger(__name__)

__all__ = ["LottieParser", "load_animation"]


def color_to_string(color):
    return "#%02X%02X%02X%02X" % tuple([int(x * 255) for x in color.components])


def fill_to_paint(fill):
    if not fill:
        return
    if isinstance(fill, objects.GradientFill):
        return gradient_fill_to_paint(fill)
    if fill.color.animated:
        logger.warning(f"Animated colour not supported")
        color = fill.color.get_value(0)
    else:
        color = fill.color.value

    color_string = color_to_string(color)

    if fill.opacity.animated:
        raise NotImplementedError
    alpha = ""
    if fill.opacity.value != 100:
        alpha = f", alpha={fill.opacity.value/100}"

    return f"PaintSolid( '{color_string}'{alpha} )"


def gradient_fill_to_paint(fill):
    if fill.gradient_type != objects.shapes.GradientType.Linear:
        pass  # raise NotImplementedError
    line = {stop: color_to_string(col) for stop, col in fill.colors.get_stops(None)}
    if fill.start_point.animated or fill.end_point.animated:
        raise NotImplementedError
    start_x, start_y = fill.start_point.get_value(0).components[:2]
    end_x, end_y = fill.end_point.get_value(0).components[:2]
    angle = (fill.start_point.value - fill.end_point.value).polar_angle + math.pi / 2
    mid_x, mid_y = start_x + math.cos(angle) * 10, start_y + math.sin(angle) * 10
    return f"PaintLinearGradient( ({start_x},{start_y}), ({end_x}, {end_y}), ({mid_x}, {mid_y}), ColorLine({line}))"


def paint_all_shapes(shapes, fill):
    layers = [f'PaintGlyph("{s}", {fill})' for s in shapes]
    if len(shapes) == 1:
        return layers[0]

    return "PaintColrLayers([" + ", ".join(layers) + "])"


def _bezier_tangent(tangent):
    _tangent_threshold = 0.5
    if tangent.length < _tangent_threshold:
        return NVector(0, 0)
    return tangent


def bez_to_layer(path, t):
    bez = path.shape.get_value(t)
    if isinstance(bez, list):
        bez = bez[0]
    layer = Layer()
    pen = layer.getPen()
    pen.moveTo(bez.vertices[0].components[:2])
    for i in range(1, len(bez.vertices)):
        qfrom = bez.vertices[i - 1]
        h1 = _bezier_tangent(bez.out_tangents[i - 1]) + qfrom
        qto = bez.vertices[i]
        h2 = _bezier_tangent(bez.in_tangents[i]) + qto
        pen.curveTo(h1.components[:2], h2.components[:2], qto.components[:2])
    if bez.closed:
        qfrom = bez.vertices[-1]
        h1 = _bezier_tangent(bez.out_tangents[-1]) + qfrom
        qto = bez.vertices[0]
        h2 = _bezier_tangent(bez.in_tangents[0]) + qto
        pen.curveTo(h1.components[:2], h2.components[:2], qto.components[:2])
    pen.closePath()
    return layer


class LottieParser(restructure.AbstractBuilder):
    def __init__(self, animation):
        super().__init__()
        self.keyframes = set()
        self._precomps = {}
        self.animation = animation

    def process(self):
        super().process(self.animation)

    def _on_animation(self, animation):
        # print("On animation", animation)
        self.result = {"layer_transform": None, "paints": [], "glyphs": {}}
        return self.result

    def _on_precomp(self, id, dom_parent, layers):
        # print("Visiting precomp", id, dom_parent, layers)
        self._precomps[id] = layers

    def _on_layer(self, layer_builder, dom_parent):
        lot = layer_builder.lottie
        # print("Visiting layer", lot)
        if lot.masks:
            self._on_masks(lot.masks)
        if lot.transform:
            dom_parent["layer_transform"] = lot.transform
        if isinstance(lot, objects.PreCompLayer):
            # print("  is precomp ", lot.reference_id)
            for layer in self._precomps.get(lot.reference_id, []):
                # print("  Processing layer", layer)
                self.process_layer(layer, dom_parent)
        return dom_parent

    def _on_masks(self, masks):
        # print("Visiting masks", masks)
        pass

    def _on_font(self, font):
        # print("Visiting font")
        pass

    def _on_layer_end(self, out_layer):
        # print("End of layer")
        # print(self.result["paints"])
        pass

    def _on_asset(self, asset):
        # print("Visiting asset", asset)
        pass

    def _on_shapegroup(self, group, dom_parent):
        # print("Visiting shapegroup", group, dom_parent)
        group.paths = []
        self.shapegroup_process_children(group, dom_parent)
        if not group.fill:
            logger.warn("Shape group with no fill in " + str(group))
            return
        # Check fill, lottie.transform, layer transform
        res = apply_transform_to_paint(
            dom_parent["layer_transform"],
            apply_transform_to_paint(
                group.lottie.transform,
                paint_all_shapes(group.paths, fill_to_paint(group.fill)),
                self.animation,
            ),
            self.animation,
        )
        dom_parent["paints"].append(res)
        return res

    def _on_merged_path(self, shape, shapegroup, out_parent):
        # print("Visiting merged path", shape, shapegroup, out_parent)
        pass

    def _on_shape(self, shape, shapegroup, out_parent):
        # print("Visiting shape", shape, shapegroup, out_parent)
        if not shapegroup:
            raise AssertionError("I thought shapes always lived in a group")
        if isinstance(
            shape, (objects.Rect, objects.Ellipse, objects.Star, objects.Path)
        ):
            path = self.to_glyph(shape.to_bezier(), shape)
            shapegroup.paths.append(path)
        return

    def to_glyph(self, path, orig_shape):
        newglyph = "glyph%04i" % (1 + len(self.result["glyphs"]))
        self.result["glyphs"][newglyph] = {"base": bez_to_layer(path, 0)}
        if path.shape.animated:
            self.result["glyphs"][newglyph]["variations"] = {
                k.time: bez_to_layer(path, k.time) for k in path.shape.keyframes
            }
            layers = list(self.result["glyphs"][newglyph]["variations"].values())
            if not all(
                len(l.shapes[0].nodes) == len(layers[0].shapes[0].nodes)
                for l in layers[1:]
            ):
                logger.warn("Bad bezier conversion")
                import IPython

                IPython.embed()
        return newglyph

    def _on_shape_modifier(self, shape, shapegroup, out_parent):
        print("Visiting shape modifier", shape, shapegroup, out_parent)
        if isinstance(shape.lottie, objects.Repeater):
            svgshape = self.build_repeater(
                shape.lottie, shape.child, shapegroup, out_parent
            )
        elif isinstance(shape.lottie, objects.RoundedCorners):
            svgshape = self.build_rounded_corners(
                shape.lottie, shape.child, shapegroup, out_parent
            )
        elif isinstance(shape.lottie, objects.Trim):
            print("Trim path not supported yet")
            return self.shapegroup_process_child(shape.child, shapegroup, out_parent)
        else:
            return self.shapegroup_process_child(shape.child, shapegroup, out_parent)
        return []

    @property
    def paint(self):
        def upside_down(p):
            return f"PaintTransform( (1, 0, 0, -1, 0, {self.animation.height}), {p})"

        if len(self.result["paints"]) == 1:
            return upside_down(self.result["paints"][0])

        return upside_down(
            "PaintColrLayers([" + ", ".join(self.result["paints"]) + "])"
        )

    @property
    def glyphs(self):
        return self.result["glyphs"]


def load_animation(path):
    return objects.Animation.load(json.load(open(path)))
