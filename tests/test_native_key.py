import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
PATH=Path(__file__).resolve().parents[1]/'work/boxlite-connect/native_key.py'
spec=importlib.util.spec_from_file_location('native_key',PATH);native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
class NativeKeyTests(unittest.TestCase):
 def test_saved_credential_is_private_even_when_replacing_existing_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'credentials.json';p.write_text('{}');p.chmod(0o644)
   native.save_key(p,'blk_test_fake_123456789')
   self.assertEqual(p.stat().st_mode & 0o777,0o600)
   self.assertEqual(json.loads(p.read_text())['BOXLITE_API_KEY'],'blk_test_fake_123456789')
 def test_cancel_preserves_saved_credential_and_does_not_start_a_web_server(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'credentials.json';p.write_text('unchanged')
   with patch.object(native,'dialog',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):native.prompt_local_key(p)
   self.assertEqual(p.read_text(),'unchanged')
 def test_optional_empty_key_does_not_overwrite_saved_key(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'credentials.json';p.write_text('unchanged')
   with patch.object(native,'dialog',return_value=''):native.prompt_local_key(p)
   self.assertEqual(p.read_text(),'unchanged')
if __name__=='__main__':unittest.main()
