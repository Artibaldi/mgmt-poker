import unittest

from poker.seal import b64u, commitment, new_halves, seal, unseal, xor


class SealTest(unittest.TestCase):
    def test_roundtrip_needs_both_halves(self):
        key, k1, k2 = new_halves()
        self.assertEqual(xor(k1, k2), key)
        blob = seal({"cards": [{"fact": "Факт ✓"}]}, key)
        self.assertNotIn("Факт", str(blob))
        self.assertEqual(unseal(blob, key)["cards"][0]["fact"], "Факт ✓")
        with self.assertRaises(ValueError):
            unseal(blob, k1)  # одной половины мало

    def test_tampering_is_detected(self):
        key, _, _ = new_halves()
        blob = seal({"x": 1}, key)
        blob["ct"] = b64u(bytes([1]) * 7)
        with self.assertRaises(ValueError):
            unseal(blob, key)

    def test_commitment_is_stable(self):
        a = commitment(3, "guest", 5, "почему", "salt")
        self.assertEqual(a, commitment(3, "guest", 5, "почему", "salt"))
        self.assertNotEqual(a, commitment(3, "guest", 8, "почему", "salt"))
        self.assertRegex(a, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
