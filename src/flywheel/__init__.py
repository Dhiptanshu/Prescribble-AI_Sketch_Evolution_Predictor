"""The model flywheel: user-consented drawings -> dataset -> retrain -> compare on real held-out drawings -> promote -> the apps pick it up.

registry.py   models/registry.json: versions, integrity hashes, promotion with an accuracy gate, rollback (python -m src.flywheel.registry ...)
onnx_eval.py  score any registered version on held-out sketches, with the same pipeline code as training and the API
gate.py       the comparison a promotion needs: shared classes, masked and unmasked, on QuickDraw and on real user drawings
dataset.py    read an export of consented user drawings and split it into train and held-out sets (stable, by drawing id)
"""
