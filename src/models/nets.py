"""Sketch models: CNN image branch, LSTM stroke branch, fusion classifier, ghost-completion decoder.

All variants share one forward signature (img, seq, length) -> (logits, recon_logits | None) so training,
evaluation and ONNX export are identical for every model.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from src.common import IMG, NUM_CLASSES, SEQ_FEATS


def conv_block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
    )


class CNNEncoder(nn.Module):
    """64x64 -> `out_dim`-d. Module III. `width` scales every channel count (1.5 = the wide variant used for the 345-class model)."""

    def __init__(self, width: float = 1.0, out_dim: int = 256):
        super().__init__()
        self.out_dim = out_dim
        c = [int(round(k * width)) for k in (16, 32, 64, 128)]
        # Stride-2 stem + narrow early stages keep it fast on a CPU (~40M MACs per sketch at width 1).
        self.body = nn.Sequential(
            nn.Conv2d(1, c[0], 3, stride=2, padding=1, bias=False), nn.BatchNorm2d(c[0]), nn.ReLU(inplace=True),  # 32
            conv_block(c[0], c[1]), nn.MaxPool2d(2),    # 16
            conv_block(c[1], c[2]), nn.MaxPool2d(2),    # 8
            conv_block(c[2], c[3]), nn.MaxPool2d(2),    # 4
        )
        self.fc = nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(c[3] * 4 * 4, out_dim), nn.ReLU(inplace=True))

    def forward(self, x):
        return self.fc(self.body(x))


class ResNetEncoder(nn.Module):
    """ImageNet-pretrained ResNet18 adapted to 1-channel 64x64 input. Module V (transfer learning)."""
    out_dim = 512

    def __init__(self, pretrained: bool = True):
        super().__init__()
        import torchvision

        weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        net = torchvision.models.resnet18(weights=weights)
        w = net.conv1.weight.data.sum(1, keepdim=True)          # RGB -> 1 channel, keeps pretrained filters
        net.conv1 = nn.Conv2d(1, 64, 7, 2, 3, bias=False)
        net.conv1.weight.data = w
        net.maxpool = nn.Identity()                              # keep resolution at 64x64
        net.fc = nn.Identity()
        self.net = net

    def forward(self, x):
        return self.net(x)


class LSTMEncoder(nn.Module):
    """Stroke-point sequence -> `hidden`-d, reading only the valid (unpadded) steps. Module IV."""

    def __init__(self, hidden: int = 128):
        super().__init__()
        self.out_dim = hidden
        self.inp = nn.Sequential(nn.Linear(SEQ_FEATS, 64), nn.ReLU(inplace=True))
        self.lstm = nn.LSTM(64, hidden, num_layers=2, batch_first=True, dropout=0.2)

    def forward(self, seq, length):
        out, _ = self.lstm(self.inp(seq))                       # (B, T, H); padding is after the valid steps
        idx = (length - 1).clamp(min=0).view(-1, 1, 1).expand(-1, 1, out.size(-1))
        return out.gather(1, idx).squeeze(1)


class GhostDecoder(nn.Module):
    """Fused feature (+ the partial raster as a skip) -> logits of the completed 64x64 drawing. Module II."""

    def __init__(self, in_dim):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(in_dim, 128 * 8 * 8), nn.ReLU(inplace=True))
        up = lambda a, b: nn.Sequential(nn.ConvTranspose2d(a, b, 4, 2, 1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True))
        self.up = nn.Sequential(up(128, 64), up(64, 32), up(32, 16))
        self.out = nn.Conv2d(16 + 1, 1, 3, padding=1)

    def forward(self, feat, img):
        x = self.up(self.fc(feat).view(-1, 128, 8, 8))
        return self.out(torch.cat([x, img], dim=1))


class SketchNet(nn.Module):
    def __init__(self, image: str | None = "cnn", sequence: bool = True, ghost: bool = True, cnn_width: float = 1.0, cnn_out: int = 256,
                 lstm_hidden: int = 128, head_hidden: int = 256):
        super().__init__()
        self.img_enc = {"cnn": lambda: CNNEncoder(cnn_width, cnn_out), "resnet": ResNetEncoder, None: None}[image]
        self.img_enc = self.img_enc() if self.img_enc else None
        self.seq_enc = LSTMEncoder(lstm_hidden) if sequence else None
        dim = (self.img_enc.out_dim if self.img_enc else 0) + (self.seq_enc.out_dim if self.seq_enc else 0)
        self.head = nn.Sequential(nn.Linear(dim, head_hidden), nn.ReLU(inplace=True), nn.Dropout(0.3), nn.Linear(head_hidden, NUM_CLASSES))
        self.ghost = GhostDecoder(dim) if ghost else None

    def forward(self, img, seq, length):
        feats = []
        if self.img_enc is not None:
            feats.append(self.img_enc(img))
        if self.seq_enc is not None:
            feats.append(self.seq_enc(seq, length))
        f = torch.cat(feats, dim=1)
        recon = self.ghost(f, img) if self.ghost is not None else None
        return self.head(f), recon


# name -> constructor kwargs. These names are the rows of the ablation table.
VARIANTS = {
    "cnn": dict(image="cnn", sequence=False, ghost=False),
    "lstm": dict(image=None, sequence=True, ghost=False),
    "fusion": dict(image="cnn", sequence=True, ghost=False),
    "fusion_ghost": dict(image="cnn", sequence=True, ghost=True),
    "resnet_ghost": dict(image="resnet", sequence=True, ghost=True),
    # The 345-class model: wider CNN, bigger sequence encoder and classifier. Same inputs and outputs, so the apps need no change.
    "fusion_ghost_xl": dict(image="cnn", sequence=True, ghost=True, cnn_width=1.5, cnn_out=384, lstm_hidden=256, head_hidden=512),
}


def build(name: str, **overrides) -> SketchNet:
    return SketchNet(**{**VARIANTS[name], **overrides})
