# from https://github.com/amdegroot/ssd.pytorch

import random as rd
import torch
from torchvision import transforms
import cv2
import numpy as np
import types
from numpy import random


def intersect(box_a, box_b):
    if box_b.ndim == 1:
        box_b = np.expand_dims(box_b, axis=0)

    if box_b.shape[0] == 0:
        # Handle empty box_b safely
        return np.zeros((box_a.shape[0], 1), dtype=np.float32)


    max_xy = np.minimum(box_a[:, 2:], box_b[0, 2:])
    min_xy = np.maximum(box_a[:, :2], box_b[0, :2])

    inter = np.clip((max_xy - min_xy), a_min=0, a_max=None)
    return inter[:, 0] * inter[:, 1]



def jaccard_numpy(box_a, box_b):
    """
    Compute the Jaccard overlap (IoU) between box_a and box_b.
    Args:
        box_a (ndarray): shape [num_boxes, 4]
        box_b (ndarray): shape [4] or [1, 4]
    Returns:
        overlaps (ndarray): shape [num_boxes]
    """
    box_a = np.atleast_2d(box_a).astype(np.float32)
    box_b = np.atleast_1d(box_b).astype(np.float32)

    if box_a.shape[0] == 0 or box_b.shape[0] == 0:
        return np.zeros((box_a.shape[0],), dtype=np.float32)

    if box_b.ndim == 1 and box_b.shape[0] == 4:
        box_b = box_b.reshape(1, 4)
    elif box_b.shape[-1] != 4:
        raise ValueError(f"box_b must be of shape [4] or [1, 4], got {box_b.shape}")

    inter = intersect(box_a, box_b[0])

    area_a = (box_a[:, 2] - box_a[:, 0]) * (box_a[:, 3] - box_a[:, 1])
    area_b = (box_b[0, 2] - box_b[0, 0]) * (box_b[0, 3] - box_b[0, 1])
    union = area_a + area_b - inter

    # Avoid division by zero
    union = np.clip(union, a_min=1e-6, a_max=None)
    return inter / union



class Compose(object):
    """Composes several augmentations together.
    Args:
        transforms (List[Transform]): list of transforms to compose.
    Example:
        >>> augmentations.Compose([
        >>>     transforms.CenterCrop(10),
        >>>     transforms.ToTensor(),
        >>> ])
    """

    def __init__(self, transforms):
        self.transforms = transforms

    def __call__(self, img, boxes=None, labels=None):
        if boxes is not None:
            boxes = np.atleast_2d(boxes)
        if boxes.shape[1] != 4:
            boxes = np.zeros((0, 4), dtype=np.float32)
        for t in self.transforms:
            img, boxes, labels = t(img, boxes, labels)
        return img, boxes, labels


class Lambda(object):
    """Applies a lambda as a transform."""

    def __init__(self, lambd):
        assert isinstance(lambd, types.LambdaType)
        self.lambd = lambd

    def __call__(self, img, boxes=None, labels=None):
        return self.lambd(img, boxes, labels)


class ConvertFromInts(object):
    def __call__(self, image, boxes=None, labels=None):
        return image.astype(np.float32), boxes, labels


class SubtractMeans(object):
    def __init__(self, mean):
        self.mean = np.array(mean, dtype=np.float32)

    def __call__(self, image, boxes=None, labels=None):
        image = image.astype(np.float32)
        image -= self.mean
        return image.astype(np.float32), boxes, labels


class ToAbsoluteCoords(object):
    def __call__(self, image, boxes=None, labels=None):
        height, width, channels = image.shape
        boxes[:, 0] *= width
        boxes[:, 2] *= width
        boxes[:, 1] *= height
        boxes[:, 3] *= height

        return image, boxes, labels


class ToPercentCoords(object):
    def __call__(self, image, boxes=None, labels=None):
        height, width, channels = image.shape
        boxes[:, 0] /= width
        boxes[:, 2] /= width
        boxes[:, 1] /= height
        boxes[:, 3] /= height

        return image, boxes, labels


class Resize(object):
    def __init__(self, size=300):
        self.size = size

    def __call__(self, image, boxes=None, labels=None):
        image = cv2.resize(image, (self.size,
                                 self.size))
        return image, boxes, labels


class RandomSaturation(object):
    def __init__(self, lower=0.5, upper=1.5):
        self.lower = lower
        self.upper = upper
        assert self.upper >= self.lower, "contrast upper must be >= lower."
        assert self.lower >= 0, "contrast lower must be non-negative."

    def __call__(self, image, boxes=None, labels=None):
        if random.randint(2):
            image[:, :, 1] *= random.uniform(self.lower, self.upper)

        return image, boxes, labels


class RandomHue(object):
    def __init__(self, delta=18.0):
        assert delta >= 0.0 and delta <= 360.0
        self.delta = delta

    def __call__(self, image, boxes=None, labels=None):
        if random.randint(2):
            image[:, :, 0] += random.uniform(-self.delta, self.delta)
            image[:, :, 0][image[:, :, 0] > 360.0] -= 360.0
            image[:, :, 0][image[:, :, 0] < 0.0] += 360.0
        return image, boxes, labels


class RandomLightingNoise(object):
    def __init__(self):
        self.perms = ((0, 1, 2), (0, 2, 1),
                      (1, 0, 2), (1, 2, 0),
                      (2, 0, 1), (2, 1, 0))

    def __call__(self, image, boxes=None, labels=None):
        if random.randint(2):
            swap = self.perms[random.randint(len(self.perms))]
            shuffle = SwapChannels(swap)  # shuffle channels
            image = shuffle(image)
        return image, boxes, labels


class ConvertColor(object):
    def __init__(self, current, transform):
        self.transform = transform
        self.current = current

    def __call__(self, image, boxes=None, labels=None):
        if self.current == 'BGR' and self.transform == 'HSV':
            image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        elif self.current == 'RGB' and self.transform == 'HSV':
            image = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        elif self.current == 'BGR' and self.transform == 'RGB':
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif self.current == 'HSV' and self.transform == 'BGR':
            image = cv2.cvtColor(image, cv2.COLOR_HSV2BGR)
        elif self.current == 'HSV' and self.transform == "RGB":
            image = cv2.cvtColor(image, cv2.COLOR_HSV2RGB)
        else:
            raise NotImplementedError
        return image, boxes, labels


class RandomContrast(object):
    def __init__(self, lower=0.5, upper=1.5):
        self.lower = lower
        self.upper = upper
        assert self.upper >= self.lower, "contrast upper must be >= lower."
        assert self.lower >= 0, "contrast lower must be non-negative."

    # expects float image
    def __call__(self, image, boxes=None, labels=None):
        if random.randint(2):
            alpha = random.uniform(self.lower, self.upper)
            image *= alpha
        return image, boxes, labels


class RandomBrightness(object):
    def __init__(self, delta=32):
        assert delta >= 0.0
        assert delta <= 255.0
        self.delta = delta

    def __call__(self, image, boxes=None, labels=None):
        if random.randint(2):
            delta = random.uniform(-self.delta, self.delta)
            image += delta
        return image, boxes, labels


class ToCV2Image(object):
    def __call__(self, tensor, boxes=None, labels=None):
        return tensor.cpu().numpy().astype(np.float32).transpose((1, 2, 0)), boxes, labels


class ToTensor(object):
    def __call__(self, cvimage, boxes=None, labels=None):
        return torch.from_numpy(cvimage.astype(np.float32)).permute(2, 0, 1), boxes, labels


class RandomSampleCrop(object):
    def __call__(self, image, boxes=None, labels=None):
        return image, boxes, labels
    # def __init__(self):
    #     self.sample_options = [
    #         (None, None),
    #         (0.1, None),
    #         (0.3, None),
    #         (0.7, None),
    #         (0.9, None),
    #         (None, None),
    #     ]



        return image, boxes, labels
    # def __call__(self, image, boxes=None, labels=None):
    #     height, width, _ = image.shape

    #     while True:  # ✅ Added retry mechanism
    #         mode = rd.choice(self.sample_options)
    #     if mode is None:
    #         return image, boxes, labels  # ✅ Fallback to original image if no crop

    #     min_iou, max_iou = mode
    #     min_iou = min_iou if min_iou is not None else float('-inf')  # ✅ Safer handling of None
    #     max_iou = max_iou if max_iou is not None else float('inf')

    #     for _ in range(50):  # ✅ Try up to 50 attempts to find a valid crop
    #         w = random.uniform(0.3 * width, width)
    #         h = random.uniform(0.3 * height, height)

    #         if h / w < 0.5 or h / w > 2:
    #             continue  # Skip non-reasonable aspect ratios

    #         left = random.uniform(0, width - w)
    #         top = random.uniform(0, height - h)

    #         rect = np.array([int(left), int(top), int(left + w), int(top + h)])
    #         overlap = jaccard_numpy(boxes, rect)

    #         # ✅ Only continue if the crop keeps overlap within bounds
    #         if overlap.min() < min_iou or overlap.max() > max_iou:
    #             continue

    #         # ✅ Check if any box center is within the crop
    #         centers = (boxes[:, :2] + boxes[:, 2:]) / 2.0
    #         m1 = (centers[:, 0] > rect[0]) * (centers[:, 1] > rect[1])
    #         m2 = (centers[:, 0] < rect[2]) * (centers[:, 1] < rect[3])
    #         mask = m1 * m2

    #         if not mask.any():  # ✅ If no boxes are retained, skip
    #             continue

    #         boxes = boxes[mask]
    #         labels = labels[mask]

    #         # ✅ Adjust box coordinates to the new crop
    #         boxes[:, :2] = np.maximum(boxes[:, :2], rect[:2])
    #         boxes[:, :2] -= rect[:2]
    #         boxes[:, 2:] = np.minimum(boxes[:, 2:], rect[2:])
    #         boxes[:, 2:] -= rect[:2]

    #         current_image = image[rect[1]:rect[3], rect[0]:rect[2], :]
    #         return current_image, boxes, labels

class Expand(object):
    def __init__(self, mean):
        self.mean = mean

    def __call__(self, image, boxes, labels):
        boxes = np.atleast_2d(boxes)
        if random.randint(2):
            return image, boxes, labels

        height, width, depth = image.shape
        ratio = random.uniform(1, 4)
        left = random.uniform(0, width*ratio - width)
        top = random.uniform(0, height*ratio - height)

        expand_image = np.zeros(
            (int(height*ratio), int(width*ratio), depth),
            dtype=image.dtype)
        expand_image[:, :, :] = self.mean
        expand_image[int(top):int(top + height),
                     int(left):int(left + width)] = image
        image = expand_image

        boxes = boxes.copy()
        boxes = np.atleast_2d(boxes)
        boxes[:, :2] += (int(left), int(top))
        boxes[:, 2:] += (int(left), int(top))

        return image, boxes, labels


class RandomMirror(object):
    def __call__(self, image, boxes, classes):
        boxes = np.atleast_2d(boxes)
        _, width, _ = image.shape
        if random.randint(2):
            image = image[:, ::-1]
            boxes = boxes.copy()
            boxes[:, 0::2] = width - boxes[:, 2::-2]
        return image, boxes, classes


class SwapChannels(object):
    """Transforms a tensorized image by swapping the channels in the order
     specified in the swap tuple.
    Args:
        swaps (int triple): final order of channels
            eg: (2, 1, 0)
    """

    def __init__(self, swaps):
        self.swaps = swaps

    def __call__(self, image):
        """
        Args:
            image (Tensor): image tensor to be transformed
        Return:
            a tensor with channels swapped according to swap
        """
        # if torch.is_tensor(image):
        #     image = image.data.cpu().numpy()
        # else:
        #     image = np.array(image)
        image = image[:, :, self.swaps]
        return image


class PhotometricDistort(object):
    def __init__(self):
        self.pd = [
            RandomContrast(),  # RGB
            ConvertColor(current="RGB", transform='HSV'),  # HSV
            RandomSaturation(),  # HSV
            RandomHue(),  # HSV
            ConvertColor(current='HSV', transform='RGB'),  # RGB
            RandomContrast()  # RGB
        ]
        self.rand_brightness = RandomBrightness()
        self.rand_light_noise = RandomLightingNoise()

    def __call__(self, image, boxes, labels):
        boxes = np.atleast_2d(boxes)
        im = image.copy()
        im, boxes, labels = self.rand_brightness(im, boxes, labels)
        if random.randint(2):
            distort = Compose(self.pd[:-1])
        else:
            distort = Compose(self.pd[1:])
        im, boxes, labels = distort(im, boxes, labels)
        return self.rand_light_noise(im, boxes, labels)

