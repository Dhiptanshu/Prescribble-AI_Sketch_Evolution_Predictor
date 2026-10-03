"""The object classes of each model generation. Pick one with PRESCRIBBLE_CLASS_SET (default v1); everything else (data folders, class
count, run folders, exported metadata) follows from it.

v1  the 30 classes of the lab project.
v2  v1 plus 70 more QuickDraw categories (all checked to exist in the 'simplified' dataset). v1's classes come first and keep their order.
v3  all 345 categories of the QuickDraw dataset: v2 plus the remaining 245. Earlier classes keep their positions, so models of different
    generations stay comparable on the classes they share.
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

# The other 245 categories of Google's QuickDraw dataset (official categories.txt order), so v3 covers every category the dataset has.
V3_EXTRA = [
    "aircraft carrier", "alarm clock", "ambulance", "angel", "animal migration", "anvil", "arm", "asparagus", "axe", "backpack", "bandage",
    "barn", "baseball", "baseball bat", "basket", "bathtub", "beach", "beard", "belt", "binoculars", "birthday cake", "blackberry",
    "blueberry", "boomerang", "bottlecap", "bracelet", "brain", "broccoli", "bulldozer", "bush", "calendar", "camel", "camouflage",
    "campfire", "cannon", "canoe", "carrot", "ceiling fan", "cello", "cell phone", "chandelier", "church", "circle", "clarinet", "compass",
    "computer", "cookie", "cooler", "couch", "crab", "crayon", "crocodile", "cruise ship", "cup", "dishwasher", "diving board", "dolphin",
    "donut", "dragon", "dresser", "drill", "drums", "dumbbell", "ear", "elbow", "eraser", "eyeglasses", "face", "fan", "feather", "finger",
    "fire hydrant", "fireplace", "firetruck", "flamingo", "flashlight", "flip flops", "floor lamp", "flying saucer", "foot", "frog",
    "frying pan", "garden", "garden hose", "goatee", "golf club", "grapes", "grass", "hamburger", "harp", "headphones", "hedgehog",
    "helmet", "hexagon", "hockey puck", "hockey stick", "horse", "hospital", "hot dog", "hot tub", "hourglass", "house plant", "hurricane",
    "jacket", "jail", "kangaroo", "keyboard", "knee", "lantern", "laptop", "leg", "lighter", "lighthouse", "line", "lipstick", "lobster",
    "lollipop", "mailbox", "map", "marker", "matches", "megaphone", "mermaid", "microwave", "mosquito", "motorbike", "mouse", "moustache",
    "mouth", "mug", "nail", "necklace", "nose", "ocean", "octagon", "onion", "oven", "paintbrush", "paint can", "palm tree", "panda",
    "paper clip", "parachute", "parrot", "passport", "peanut", "pear", "peas", "pencil", "piano", "pickup truck", "picture frame", "pillow",
    "pineapple", "pliers", "police car", "pond", "pool", "popsicle", "postcard", "potato", "power outlet", "purse", "raccoon", "radio",
    "rain", "rake", "remote control", "rhinoceros", "rifle", "river", "roller coaster", "rollerskates", "sandwich", "saw", "saxophone",
    "school bus", "scorpion", "screwdriver", "sea turtle", "see saw", "shark", "sheep", "shorts", "shovel", "sink", "skateboard",
    "skyscraper", "sleeping bag", "snail", "snorkel", "snowflake", "soccer ball", "sock", "speedboat", "spreadsheet", "square", "squiggle",
    "squirrel", "stairs", "steak", "stereo", "stethoscope", "stitches", "stop sign", "stove", "streetlight", "string bean", "suitcase",
    "swan", "sweater", "swing set", "syringe", "teapot", "teddy-bear", "telephone", "television", "tennis racquet", "The Eiffel Tower",
    "The Great Wall of China", "The Mona Lisa", "tiger", "toaster", "toe", "toilet", "tooth", "toothbrush", "toothpaste", "tornado",
    "traffic light", "triangle", "trombone", "trumpet", "t-shirt", "underwear", "van", "vase", "violin", "washing machine", "waterslide",
    "wheel", "wine bottle", "wristwatch", "yoga", "zigzag",
]

CLASS_SETS = {"v1": V1, "v2": V1 + V2_EXTRA, "v3": V1 + V2_EXTRA + V3_EXTRA}
assert len(CLASS_SETS["v2"]) == 100 and len(set(CLASS_SETS["v2"])) == 100
assert len(CLASS_SETS["v3"]) == 345 and len(set(CLASS_SETS["v3"])) == 345
