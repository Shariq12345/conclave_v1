"""Real federated-learning workloads used by Conclave Flower clients.

The workload is deliberately independent of the server process: every client
derives the same deterministic partition from the public CIFAR-10 labels, then
trains only on its own assigned subset. Images are never sent to the server.
"""

from __future__ import annotations

import os
from typing import Tuple

import numpy as np

try:
    import torch
    from torch.utils.data import DataLoader, Subset
    from torchvision import datasets, models, transforms
    HAS_TORCHVISION = True
except ImportError:  # pragma: no cover
    HAS_TORCHVISION = False


SUPPORTED_REAL_DATASETS = {"cifar10", "cifar-10"}


def is_real_workload(dataset_name: str) -> bool:
    """Return whether a dataset name selects a real vision workload."""
    return dataset_name.strip().lower() in SUPPORTED_REAL_DATASETS


def build_cifar10_resnet18(num_classes: int = 10):
    """Build a CIFAR-10 sized ResNet-18 without downloading pretrained weights."""
    if not HAS_TORCHVISION:
        raise RuntimeError("CIFAR-10 workloads require torch and torchvision to be installed.")
    model = models.resnet18(weights=None)
    model.conv1 = torch.nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
    model.maxpool = torch.nn.Identity()
    model.fc = torch.nn.Linear(model.fc.in_features, num_classes)
    return model


def _partition_indices(labels: np.ndarray, num_clients: int, client_index: int, alpha: float, seed: int) -> np.ndarray:
    """Create a deterministic Dirichlet label-skew partition for one client."""
    if num_clients < 1 or not 0 <= client_index < num_clients:
        raise ValueError("client_index must identify one of the participating clients.")
    if alpha <= 0:
        raise ValueError("dirichlet_alpha must be greater than zero.")
    rng = np.random.default_rng(seed)
    partitions = [[] for _ in range(num_clients)]
    for label in np.unique(labels):
        indices = np.flatnonzero(labels == label)
        rng.shuffle(indices)
        proportions = rng.dirichlet(np.full(num_clients, alpha))
        boundaries = (np.cumsum(proportions) * len(indices)).astype(int)[:-1]
        for idx, split in enumerate(np.split(indices, boundaries)):
            partitions[idx].extend(split.tolist())
    selected = np.asarray(partitions[client_index], dtype=np.int64)
    if not len(selected):
        selected = np.asarray([int(rng.integers(0, len(labels)))], dtype=np.int64)
    rng.shuffle(selected)
    return selected


def load_cifar10_partition(*, client_index: int, num_clients: int, data_dir: str | None = None,
                           dirichlet_alpha: float = 0.5, seed: int = 42, batch_size: int = 32,
                           num_workers: int = 0, download: bool = True) -> Tuple[DataLoader, DataLoader]:
    """Load one client's non-IID CIFAR-10 train partition and shared test set."""
    if not HAS_TORCHVISION:
        raise RuntimeError("CIFAR-10 workloads require torch and torchvision to be installed.")
    root = data_dir or os.getenv("CONCLAVE_DATA_DIR", os.path.expanduser("~/.conclave/data"))
    train_transform = transforms.Compose([transforms.RandomCrop(32, padding=4), transforms.RandomHorizontalFlip(), transforms.ToTensor(), transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616))])
    test_transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616))])
    try:
        train_dataset = datasets.CIFAR10(root=root, train=True, download=download, transform=train_transform)
        test_dataset = datasets.CIFAR10(root=root, train=False, download=download, transform=test_transform)
    except Exception as exc:
        raise RuntimeError(f"Unable to load CIFAR-10 in '{root}'. Set CONCLAVE_DATA_DIR to a writable dataset cache or enable network access for the initial download.") from exc
    indices = _partition_indices(np.asarray(train_dataset.targets), num_clients, client_index, dirichlet_alpha, seed)
    return (DataLoader(Subset(train_dataset, indices.tolist()), batch_size=batch_size, shuffle=True, num_workers=num_workers),
            DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers))
