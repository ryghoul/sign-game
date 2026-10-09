import json
import tempfile
import unittest
from pathlib import Path
from maps import validate_map, save_map, map_path

class MapTests(unittest.TestCase):
    def sample(self):
        return {'name':'My map','signs':['serpent','tiger','monkey','hare','dragon'],
                'notes':[{'time':2,'duration':.5,'lane':1,'signSlot':3},
                         {'time':1,'duration':0,'lane':0,'signSlot':0}]}

    def test_save_sorts_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            saved=save_map(root,'track-1',self.sample(),10)
            self.assertEqual(saved['notes'][0]['time'],1)
            self.assertEqual(json.loads(map_path(root,'track-1').read_text()),saved)

    def test_invalid_notes_and_paths(self):
        for property,value in [('time',-1),('duration',float('nan')),('lane',4),('signSlot',5),('duration',20)]:
            sample=self.sample();sample['notes'][0][property]=value
            with self.assertRaises(ValueError):validate_map(sample,10)
        with self.assertRaises(ValueError):map_path(Path('.'),'../outside')

    def test_failure_preserves_previous_map(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);save_map(root,'track-1',self.sample(),10)
            before=map_path(root,'track-1').read_text()
            invalid=self.sample();invalid['notes']=[]
            with self.assertRaises(ValueError):save_map(root,'track-1',invalid,10)
            self.assertEqual(map_path(root,'track-1').read_text(),before)
