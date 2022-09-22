# lottie2vf

This is a simple `.lottie` to animated variable font convertor.
It's a work in progress; it may or may not support your Lottie file, but it'll do its best:

    pip3 install -r requirements.txt
    python3 -m lottie2vf file.lottie

## What should work

* Plain colour fills
* Linear gradients
* Basic rotate/scale/translate/opacity animations

## What doesn't yet work

* Animated anchors
* Radial gradients
* Strokes (not supported in COLRv1)
* Trim paths (not supported in COLRv1 as far as I know)

## License

Apache 2.0, see `LICENSE` for terms

