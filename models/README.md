# Fruit Counter model

The Fruit Counter counts with **MobileSAM**, a small version of Meta's Segment Anything model, run on the
computer's processor with onnxruntime. It outlines things in a picture; `apps/fruit_model.py` decides which
outlines are the things to count.

| File | What it is |
|---|---|
| `mobile_sam_image_encoder.onnx` | Reads a picture once (about half a second) |
| `sam_mask_decoder_multi.onnx` | Outlines the thing at a point or in a box (about 0.03 s per question) |

Licences: MobileSAM (https://github.com/ChaoningZhang/MobileSAM) and Segment Anything
(https://github.com/facebookresearch/segment-anything) are Apache-2.0. These ONNX files were exported from the
MobileSAM weights (https://huggingface.co/dhkim2810/MobileSAM) and published under the MIT licence.

Without these files the Fruit Counter still works, with the plain counter (less accurate, no count modes for groups).
