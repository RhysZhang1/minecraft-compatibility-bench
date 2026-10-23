# SPDX-License-Identifier: GPL-3.0-or-later
import os
import unittest
from unittest.mock import patch

from mcbench import model_config as model_config
from mcbench.tools import manage, serve_model


class ProfileTests(unittest.TestCase):
    def test_full_gpu_2b_weights_and_vision(self):
        with patch.dict(os.environ, {"MODEL_GPU_LAYERS": "99", "MODEL_VISION_GPU": "1"}):
            cmd, meta = serve_model.launch_config(model_config.config("2b"), "balanced")
        self.assertEqual(cmd[cmd.index("--override-tensor") + 1], ".*=CUDA0")
        self.assertIn("--mmproj-offload", cmd)
        self.assertTrue(meta["all_tensors_gpu"])
        self.assertEqual(cmd[cmd.index("--cache-ram") + 1], "0")
        self.assertTrue(manage.matches("model", cmd, manage.ROOT))

    def test_cpu_never_forces_cuda_tensors(self):
        with patch.dict(os.environ, {"MODEL_GPU_LAYERS": "99", "MODEL_VISION_GPU": "1"}):
            cmd, meta = serve_model.launch_config(model_config.config("2b"), "cpu")
        self.assertNotIn("--override-tensor", cmd)
        self.assertEqual(cmd[cmd.index("--device") + 1], "none")
        self.assertEqual(cmd[cmd.index("--gpu-layers") + 1], "0")
        self.assertIn("--no-mmproj-offload", cmd)
        self.assertFalse(meta["vision_gpu"])

    def test_9b_retains_partial_offload(self):
        with patch.dict(os.environ, {"MODEL_GPU_LAYERS": "8", "MODEL_VISION_GPU": "1"}):
            cmd, meta = serve_model.launch_config(model_config.config("9b"), "balanced")
        self.assertNotIn("--override-tensor", cmd)
        self.assertEqual(cmd[cmd.index("--gpu-layers") + 1], "8")
        self.assertTrue(manage.matches("model", cmd, manage.ROOT))
        self.assertFalse(meta["all_tensors_gpu"])


if __name__ == "__main__":
    unittest.main()
