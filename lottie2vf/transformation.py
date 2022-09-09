import logging
import math
from lottie.utils.transform import TransformMatrix


logger = logging.getLogger(__name__)


def animated_value_to_ot(keyframes, animation):
    values = [""] * len(keyframes[0].start.components)
    for ix in range(len(values)):
        if all(
            [
                keyframes[0].start.components[ix] == k.start.components[ix]
                for k in keyframes
                if k.start
            ]
        ):
            # This isn't animated
            values[ix] = keyframes[0].start.components[ix]
        else:
            seen = set()
            for k in keyframes:
                if not k.start:
                    continue
                v = k.start.components[ix]
                if k.time < 0:
                    k.time = 0
                if k.time > animation.out_point:
                    k.time = animation.out_point
                if k.time in seen:
                    continue
                seen.add(k.time)
                values[ix] += f"ANIM:{k.time}={v} "
            values[ix] = f'"{values[ix]}"'
    return values


def scale_to_paint(transform, paint, animation):
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
        if scale.value.x > 2:
            logger.warn(
                f"Oversized scale {k.start} found; clipping to 2; need to implement PaintVarTransform"
            )
            scale.value.x = 1.99

        if has_anchor:
            return f"PaintScaleAroundCenter( {scale.value.x}, {scale.value.y}, ({anchor.value.x}, {anchor.value.y}), {paint})"
        else:
            return f"PaintScale( {scale.value.x}, {scale.value.y}, {paint})"

    # Scale down the scale
    scale = scale.clone()
    for k in scale.keyframes:
        k.start /= 100
        if k.start.x >= 2:
            logger.warn(
                f"Oversized scale {k.start} found; clipping to 2; need to implement PaintVarTransform"
            )
            k.start.x = 1.99
        if k.start.y >= 2:
            logger.warn(
                f"Oversized scale {k.start} found; clipping to 2; need to implement PaintVarTransform"
            )
            k.start.y = 1.99

    animated_scale = animated_value_to_ot(scale.keyframes, animation)
    if anchor.animated:
        raise NotImplementedError

    if has_anchor:
        return f"PaintVarScaleAroundCenter( {animated_scale[0]}, {animated_scale[1]}, ({anchor.value.x}, {anchor.value.y }), {paint})"
    else:
        return f"PaintVarScale( {animated_scale[0]}, {animated_scale[1]}, {paint})"


def rotation_to_paint(transform, paint, animation):
    rotation = transform.rotation
    anchor = transform.anchor_point
    has_anchor = anchor and (
        anchor.animated or any(x != 0 for x in anchor.value.components)
    )
    animated = rotation.animated or (anchor and anchor.animated)

    if not animated and rotation.value == 0.0:
        return paint

    if animated:
        if anchor.animated:
            logger.warn("Animated rotation not implemented")
            raise NotImplementedError
        rotation = rotation.clone()
        for k in rotation.keyframes:
            k.start.components[0] = math.radians(-k.start.components[0]) / math.pi
        animated_rotation = animated_value_to_ot(rotation.keyframes, animation)
        if has_anchor:
            return f"PaintVarRotateAroundCenter( {animated_rotation[0]}, ({anchor.value.x}, {anchor.value.y }), {paint})"
        else:
            return f"PaintVarRotate( {animated_rotation[0]}, {paint})"

    angle = math.radians(-rotation.value) / math.pi
    if has_anchor:
        return f"PaintRotateAroundCenter( {angle}, ({anchor.value.x}, {anchor.value.y}), {paint})"
    else:
        return f"PaintRotate( {angle}, {paint})"


def position_to_paint(transform, paint, animation):
    position = transform.position
    animated = position.animated

    if not animated and all(x == 0 for x in position.value.components):
        return paint

    if not animated:
        return f"PaintTranslate( {position.value.x}, {position.value.y}, {paint})"

    animated_pos = animated_value_to_ot(position.keyframes, animation)
    return f"PaintVarTranslate( {animated_pos[0]}, {animated_pos[1]}, {paint})"


def matrix_to_paint(matrix, paint):
    if matrix.to_css_2d() == TransformMatrix().to_css_2d():
        return paint
    return f"""PaintTransform((
        {matrix.a}, { matrix.b }, {matrix.c}, {matrix.d},
        {matrix.tx}, { matrix. ty}
    ), {paint} )"""


def apply_transform_to_paint(transform, paint, animation):
    frames = (
        (transform.scale.keyframes or [])
        + (transform.position.keyframes or [])
        + (transform.rotation.keyframes or [])
    )
    if not frames:
        return matrix_to_paint(transform.to_matrix(0), paint)

    return scale_to_paint(
        transform,
        rotation_to_paint(
            transform, position_to_paint(transform, paint, animation), animation
        ),
        animation,
    )
