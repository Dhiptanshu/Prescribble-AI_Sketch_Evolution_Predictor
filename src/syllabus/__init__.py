"""Experiments that close the course-syllabus gaps (Modules II, III and V). Each file is runnable:

python -m src.syllabus.digit_cnn      # III  CNN digit classification (MNIST)
python -m src.syllabus.ae             # II   convolutional autoencoder, bottleneck study, denoising
python -m src.syllabus.vae            # II   variational autoencoder, latent manifold, beta study
python -m src.syllabus.gan            # II   DCGAN on MNIST, scored with the digit CNN
python -m src.syllabus.detection.train_scratch   # III  YOLO-style object detector written from scratch
python -m src.syllabus.detection.train_yolov8    # V    YOLOv8n transfer learning on the same scenes
python -m src.syllabus.vgg_transfer   # V    VGG16 transfer learning on sketches (vs the ResNet18 result)

Every script takes --smoke (tiny run to check the pipeline) and runs on CPU or GPU. Results go to runs/syllabus/<name>/results.json,
figures to report/figures/syllabus_*.png. The Kaggle driver is kaggle/syllabus/run_syllabus.py.
"""
