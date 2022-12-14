from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fontTools.misc.timeTools import epoch_diff, timestampSinceEpoch
from cu2qu.ufo import glyphs_to_quadratic
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.models import VariationModel
from fontTools.misc.fixedTools import otRound
from functools import partial


UPM = 1000


def font_builder(an):
    fb = FontBuilder(an.height, isTTF=True)  # Or maybe UPM
    fb._an = an

    fb.setupHorizontalHeader(
        ascent=an.height,
        descent=0,
    )
    fb.setupNameTable({})
    fb.setupFvar(
        axes=[("ANIM", an.in_point, an.in_point, an.out_point, "Frame")], instances=[]
    )
    return fb


def add_glyphs(fb, glyphs):
    glyf = {}
    fb.setupGlyphOrder([".notdef", "baseglyph"] + list(glyphs.keys()))

    # This zero is clearly wrong

    glyphset = {}

    # Empty glyf base glyph
    pen = TTGlyphPen(None)
    glyphset[".notdef"] = pen.glyph()
    glyphset["baseglyph"] = pen.glyph()
    variations = {}

    metrics = {".notdef": (0, fb._an.width), "baseglyph": (0, fb._an.width)}
    for glyphname, glyph in glyphs.items():
        if glyph.get("variations"):
            keyframes = list(sorted(glyph["variations"].keys()))
            glyphs_to_quadratic(glyph["variations"].values(), reverse_direction=True)
            glyph["base"] = glyph["variations"][keyframes[0]]
            frames = [{"ANIM": k / fb._an.out_point} for k in keyframes]
            ttglyphs = []
            if {"ANIM": 0} not in frames:
                pen = TTGlyphPen(None)
                glyph["base"].draw(pen)
                ttglyphs.append(pen.glyph())
                frames.insert(0, {"ANIM": 0})
            model = VariationModel(frames)
            for k in keyframes:
                pen = TTGlyphPen(None)
                glyph["variations"][k].draw(pen)
                ttglyphs.append(pen.glyph())
            variations[glyphname] = calculate_a_gvar(glyphname, fb, model, ttglyphs)
        else:
            glyphs_to_quadratic([glyph["base"]], reverse_direction=True)
        pen = TTGlyphPen(None)
        glyph["base"].draw(pen)
        glyphset[glyphname] = pen.glyph()

        metrics[glyphname] = (fb._an.width, glyph["base"].lsb)

    fb.setupHorizontalMetrics(metrics)
    fb.setupGlyf(glyphset)
    if variations:
        fb.setupGvar(variations)
    fb.setupCharacterMap({97: "baseglyph"})
    fb.setupOS2(
        sTypoAscender=fb._an.height,
        sTypoDescender=0,
        sCapHeight=fb._an.height,
        sxHeight=fb._an.height,
    )
    fb.updateHead(
        fontRevision=1.000,
        # created=timestampSinceEpoch(f.date.timestamp()),
        lowestRecPPEM=10,
    )
    fb.setupPost()

    pass


def calculate_a_gvar(g, fb, model, ttglyphs):
    all_coords = []
    for ttglyph in ttglyphs:
        basecoords = GlyphCoordinates(ttglyph.coordinates)
        phantomcoords = GlyphCoordinates(
            [(0, 0), (otRound(fb._an.width), 0), (0, 0), (0, 0)]
        )
        basecoords.extend(phantomcoords)
        all_coords.append(basecoords)
    for ix, c in enumerate(all_coords):
        all_ok = True
        if len(c) != len(all_coords[0]):
            print("Incompatible master %i in glyph %s" % (ix, g))
            all_ok = False
        if not all_ok:
            return []
    deltas = model.getDeltas(
        all_coords,
        round=partial(GlyphCoordinates.__round__, round=round),
    )
    gvar_entry = []
    endPts = ttglyphs[0].endPtsOfContours

    for delta, sup in zip(deltas, model.supports):
        if not sup:
            continue
        var = TupleVariation(sup, delta)
        gvar_entry.append(var)
    return gvar_entry
