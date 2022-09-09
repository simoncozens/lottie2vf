from lottie.utils import restructure
from lottie.nvector import NVector
from lottie import objects
import json
import sys
import logging
from babelfont import Layer


logger = logging.getLogger(__name__)

__all__ = ["LottieParser", "load_animation"]


def animated_value_to_ot(keyframes):
    values = [""] * len(keyframes[0].start.components)
    for ix in range(len(values)):
        if all(
            [
                keyframes[0].start.components[ix] == k.start.components[ix]
                for k in keyframes
            ]
        ):
            # This isn't animated
            values[ix] = keyframes[0].start.components[ix]
        else:
            for k in keyframes:
                v = k.start.components[ix]
                values[ix] += f"ANIM:{k.time}={v} "
            values[ix] = f'"{values[ix]}"'
    return values


def scale_to_paint(transform, paint):
    scale = transform.scale
    anchor = transform.anchor_point
    has_anchor = anchor and (
        anchor.animated or any(x != 0 for x in anchor.value.components)
    )
    animated = scale.animated or (anchor and anchor.animated)

    if not animated and all(x == 100 for x in scale.value.components):
        return paint

    if not animated:
        # Scale down the scale
        scale = scale.clone()
        scale.value /= 100
        if has_anchor:
            return f"PaintScaleAroundCenter( {scale.value.x}, {scale.value.y}, ({anchor.value.x}, {anchor.value.y}), {paint})"
        else:
            return f"PaintScale( {scale.value.x}, {scale.value.y}, {paint})"

    # Scale down the scale
    scale = scale.clone()
    for k in scale.keyframes:
        k.start /= 100

    animated_scale = animated_value_to_ot(scale.keyframes)
    if anchor.animated:
        raise NotImplementedError

    if has_anchor:
        return f"PaintVarScaleAroundCenter( {animated_scale[0]}, {animated_scale[1]}, ({anchor.value.x / 100}, {anchor.value.y / 100}), {paint})"
    else:
        return f"PaintVarScale( {animated_scale[0]}, {animated_scale[1]}, {paint})"


def rotation_to_paint(transform, paint):
    rotation = transform.rotation
    anchor = transform.anchor_point
    has_anchor = anchor and (
        anchor.animated or any(x != 0 for x in anchor.value.components)
    )
    animated = rotation.animated or (anchor and anchor.animated)

    if not animated and rotation.value == 0.0:
        return paint

    import IPython

    IPython.embed()


def position_to_paint(transform, paint, animation):
    position = transform.position
    animated = position.animated

    if not animated and all(x == 0 for x in position.value.components):
        return paint

    if not animated:
        return f"PaintTranslate( {position.value.x}, {position.value.y}, {paint})"

    animated_pos = animated_value_to_ot(position.keyframes)
    return f"PaintVarTranslate( {animated_pos[0]}, {animated_pos[1]}, {paint})"


def apply_transform_to_paint(transform, paint, animation):
    if not transform:
        return paint
    return position_to_paint(
        transform,
        rotation_to_paint(transform, scale_to_paint(transform, paint)),
        animation,
    )


def fill_to_paint(fill):
    if not fill:
        return
    if fill.color.animated:
        logger.warning(f"Animated colour not supported")
        color = fill.color.get_value(0) * 255
    else:
        color = fill.color.value * 255
    color_string = "#%02X%02X%02X%02X" % tuple([int(x) for x in color.components])

    if fill.opacity.animated:
        raise NotImplementedError
    alpha = ""
    if fill.opacity.value != 100:
        alpha = f", alpha={fill.opacity.value/100}"

    return f"PaintSolid( '{color_string}'{alpha} )"


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
    # if bez.closed:
    #     qfrom = bez.vertices[-1]
    #     h1 = _bezier_tangent(bez.out_tangents[-1]) + qfrom
    #     qto = bez.vertices[0]
    #     h2 = _bezier_tangent(bez.in_tangents[0]) + qto
    #     pen.curveTo(h1.components[:2], h2.components[:2], qto.components[:2])
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
                self.process_layer(layer, [])
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
            path = self.to_glyph(shape.to_bezier())
            shapegroup.paths.append(path)
        return

    def to_glyph(self, path):
        newglyph = "glyph%04i" % (1 + len(self.result["glyphs"]))
        self.result["glyphs"][newglyph] = {"base": bez_to_layer(path, 0)}
        if path.shape.animated:
            self.result["glyphs"][newglyph]["variations"] = {
                k.time: bez_to_layer(path, k.time) for k in path.shape.keyframes
            }
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
        if len(self.result["paints"]) == 1:
            return self.result["paints"][0]

        return "PaintColrLayers([" + ", ".join(self.result["paints"]) + "])"

    @property
    def glyphs(self):
        return self.result["glyphs"]


def load_animation(path):
    return objects.Animation.load(json.load(open(path)))
