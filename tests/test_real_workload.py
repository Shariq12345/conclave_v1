import unittest
from unittest.mock import patch

import numpy as np

from conclave.integrations.flower.workloads import (
    _partition_indices,
    build_cifar10_resnet18,
    is_real_workload,
)


class RealWorkloadTests(unittest.TestCase):
    def test_cifar10_aliases_select_the_real_workload(self):
        self.assertTrue(is_real_workload("cifar10"))
        self.assertTrue(is_real_workload(" CIFAR-10 "))
        self.assertFalse(is_real_workload("diabetes"))

    def test_dirichlet_partition_is_reproducible_and_complete(self):
        labels = np.repeat(np.arange(10), 20)
        first = [_partition_indices(labels, 4, client, 0.5, 42) for client in range(4)]
        second = [_partition_indices(labels, 4, client, 0.5, 42) for client in range(4)]
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(sum(len(indices) for indices in first), len(labels))
        self.assertEqual(len(np.unique(np.concatenate(first))), len(labels))

    def test_resnet18_accepts_cifar10_tensors(self):
        import torch
        model = build_cifar10_resnet18()
        logits = model(torch.zeros(2, 3, 32, 32))
        self.assertEqual(tuple(logits.shape), (2, 10))

    def test_pytorch_client_trains_a_cifar10_partition(self):
        import torch
        from torch.utils.data import DataLoader, TensorDataset
        from conclave.integrations.flower.orchestrator import PyTorchFlowerClient

        images = torch.zeros(4, 3, 32, 32)
        labels = torch.tensor([0, 1, 2, 3])
        loader = DataLoader(TensorDataset(images, labels), batch_size=2)
        with patch("conclave.integrations.flower.orchestrator.load_cifar10_partition", return_value=(loader, loader)):
            client = PyTorchFlowerClient(
                "client-1",
                {"dataset_name": "cifar10", "client_index": 0, "client_names": ["client-1"], "local_epochs": 0},
            )
            parameters = client.get_parameters({})
            updated, examples, metrics = client.fit(parameters, {})

        self.assertEqual(examples, 4)
        self.assertEqual(len(updated), len(parameters))
        self.assertIn("accuracy", metrics)


if __name__ == "__main__":
    unittest.main()
