import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from sparkmd.config import Config
from sparkmd.worker import Worker


def dicom(directory, study_uid, series_uid, sop_uid=None, *, patient='synthetic', date='20000102', kernel='B30f', modality='CT'):
    directory.mkdir(parents=True, exist_ok=True)
    sop_uid = sop_uid or generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    path = directory/(sop_uid+'.dcm')
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0'*128)
    ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, sop_uid
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series_uid
    ds.PatientID, ds.StudyDate, ds.Modality = patient, date, modality
    ds.ConvolutionKernel, ds.SliceThickness = kernel, 2
    ds.ImageOrientationPatient = [1,0,0,0,1,0]
    ds.ImageType = ['ORIGINAL','PRIMARY','AXIAL']
    ds.save_as(path, enforce_file_format=True)
    return path


class WorkerState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.worker = Worker(Config(home=self.home, fake=True, fake_seed=True, fake_seconds=0))
        self.addCleanup(self.worker.registry.close)

    def test_intake_extended_delivery_and_duplicate(self):
        uid, sid = generate_uid(), generate_uid()
        source = self.home/'inbox'/'incoming'
        for _ in range(100): dicom(source, uid, sid)
        self.assertEqual(self.worker.intake.ingest_study(source), uid)
        self.assertEqual(self.worker.registry.one('SELECT n_instances FROM series WHERE series_uid=?', (sid,))['n_instances'], 100)
        # The initial files were moved away; a resumed copy contains just the new slice.
        new_file = dicom(source, uid, sid)
        sop = new_file.stem
        self.worker.intake.ingest_study(source)
        self.assertEqual(self.worker.registry.one('SELECT n_instances FROM series WHERE series_uid=?', (sid,))['n_instances'], 101)
        dicom(source, uid, sid, sop)
        self.worker.intake.ingest_study(source)
        self.assertEqual(self.worker.registry.one('SELECT n_instances FROM series WHERE series_uid=?', (sid,))['n_instances'], 101)
        self.assertEqual(len(self.worker.registry.all('SELECT * FROM studies WHERE study_uid=?', (uid,))), 1)

    def test_intake_timepoint_rerank_and_real_offsets(self):
        (self.home/'day_offsets.csv').write_text('patient_id,rank,day_offset\nsynthetic,0,23\nsynthetic,1,394\n')
        later, earlier = generate_uid(), generate_uid()
        for uid, date in [(later, '20000102'), (earlier, '19990102')]:
            source = self.home/'inbox'/uid
            sid = generate_uid()
            for _ in range(100): dicom(source, uid, sid, date=date)
            self.worker.intake.ingest_study(source)
        rows = self.worker.registry.all("SELECT timepoint,day_offset,day_offset_source FROM studies WHERE patient_id='synthetic' ORDER BY rank")
        self.assertEqual(rows, [{'timepoint':'T0','day_offset':23,'day_offset_source':'sidecar'}, {'timepoint':'T1','day_offset':394,'day_offset_source':'sidecar'}])

    def test_invalid_intake_records_failure(self):
        source = self.home/'inbox'/'bad'
        source.mkdir()
        (source/'broken.dcm').write_bytes(b'not DICOM')
        with self.assertRaisesRegex(ValueError, 'no readable DICOM'):
            self.worker.intake.ingest_study(source)
        row = self.worker.registry.one("SELECT status,failure_reason FROM studies WHERE patient_id='unknown'")
        self.assertEqual(row['status'], 'failed')
        self.assertIn('no readable DICOM', row['failure_reason'])

    def test_approve_unconfirmed_409_has_no_report(self):
        with self.worker.registry.transaction() as db:
            db.execute("INSERT INTO reports(report_id,study_uid,kind,markdown,version) VALUES ('pending','fixture-T0','pcp_letter','pending',1)")
        payload, code = self.worker.approve('pending', {'approver':'human'})
        self.assertEqual(code, 409)
        self.assertEqual(payload, {'error':'confirm_all_first','already_approved':False})
        self.assertEqual(self.worker.registry.all('SELECT * FROM outbox'), [])

    def test_unknown_offsets_never_use_calendar_dates(self):
        for uid, size in [('fixture-T0',10), ('fixture-T1',14)]:
            asyncio.run(self.worker.call_tool('select_series', {'study_uid':uid,'series_uid':uid+'-soft','reason':'test'}))
            asyncio.run(self.worker.analyze(uid, 5))
            with self.worker.registry.transaction() as db:
                db.execute('UPDATE studies SET day_offset=NULL WHERE study_uid=?', (uid,))
            value, code = self.worker.confirm(uid+'-N1', {'long_mm':size,'short_mm':size,'by':'human'})
            self.assertEqual(code, 200)
        prior = value['nodules'][0]['prior']
        self.assertIsNone(prior['interval_days'])
        self.assertIsNone(prior['growth_per_12mo_mm'])
        self.assertIsNone(prior['vdt_days'])
        self.assertEqual(value['assessment']['lung_rads'], '4A')


if __name__ == '__main__':
    unittest.main()
