"""The object classes of each model generation. Pick one with PRESCRIBBLE_CLASS_SET (default v1); everything else (data folders, class
count, run folders, exported metadata) follows from it.

v1  the 30 classes of the lab project.
v2  v1 plus 70 more QuickDraw categories (all checked to exist in the 'simplified' dataset). v1's classes come first and keep their order.
"""
V1 = [
    "cat", "dog", "house", "sun", "flower", "tree", "car", "bicycle", "airplane", "fish",
    "bird", "apple", "banana", "umbrella", "clock", "star", "moon", "coffee cup", "chair", "table",
    "guitar", "envelope", "key", "light bulb", "mushroom", "butterfly", "snowman", "pizza",
    "smiley face", "ice cream",
]

V2_EXTRA = [
    "ant", "bear", "bed", "bee", "book", "bread", "bridge", "bus", "cake", "camera", "candle", "castle", "cloud", "cow", "crown",
    "diamond", "door", "duck", "elephant", "eye", "fence", "fork", "giraffe", "hat", "hammer", "hand", "helicopter", "hot air balloon",
    "knife", "ladder", "leaf", "lightning", "lion", "microphone", "monkey", "mountain", "octopus", "owl", "pants", "penguin", "pig",
    "rabbit", "rainbow", "sailboat", "scissors", "shoe", "skull", "snake", "spider", "spoon", "strawberry", "submarine", "sword", "tent",
    "tractor", "train", "truck", "watermelon", "whale", "windmill", "wine glass", "zebra", "bat", "bucket", "calculator", "cactus",
    "bench", "basketball", "bowtie", "broom",
]

CLASS_SETS = {"v1": V1, "v2": V1 + V2_EXTRA}
assert len(CLASS_SETS["v2"]) == 100 and len(set(CLASS_SETS["v2"])) == 100
