import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'lab/render.py'
SPEC = importlib.util.spec_from_file_location('lab_render', PATH)
LAB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAB)


class LabBoundaryTests(unittest.TestCase):
    def test_rejects_exposure_credential_generation_and_namespace_escape(self):
        for obj in [
            {'kind': 'Service', 'metadata': {'name': 'test', 'namespace': LAB.NAMESPACE},
             'spec': {'type': 'NodePort'}},
            {'kind': 'Secret', 'metadata': {'name': 'test', 'namespace': LAB.NAMESPACE},
             'stringData': {'password': 'SYNTHETIC'}},
            {'kind': 'Service', 'metadata': {'name': 'test', 'namespace': 'default'}},
            {'kind': 'ClusterRole', 'metadata': {'name': 'test', 'namespace': LAB.NAMESPACE}},
        ]:
            with self.subTest(kind=obj['kind']), self.assertRaises(ValueError):
                LAB.bounded([obj])


if __name__ == '__main__':
    unittest.main()
