"""Object detection on 'MNIST scenes': 128x128 canvases holding 1-4 real MNIST digits of different sizes at random places.

The scenes are composed from real handwritten digits (train scenes from the MNIST training digits, validation scenes from the test digits, so no
digit is shared) and every box is measured from the pasted pixels, so labels are exact. Three detectors are compared on the same validation scenes
with the same metric (metrics.py): one written from scratch (yolo_lite.py), YOLOv8n trained from scratch, and YOLOv8n fine-tuned from COCO weights.
"""
