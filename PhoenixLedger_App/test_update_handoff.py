"""Headless regression tests: old app must not close before validated handoff."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import businessdesk

class UpdaterHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data=Path(self.tmp.name)
        (self.data/'updates').mkdir()
        self.patch_data=patch.object(businessdesk,'DATA',self.data)
        self.patch_data.start()
        self.addCleanup(self.patch_data.stop)
        self.events=[]
        self.app=businessdesk.PhoenixLedger.__new__(businessdesk.PhoenixLedger)
        self.app.root=Mock()
        self.app.db=Mock()
        self.app._update_attempt='f'*32
        self.app._update_handoff=self.data/'updates'/('handoff_'+self.app._update_attempt+'.ready')
        self.app._update_worker=Mock()
        self.app._update_worker.poll.return_value=None
        self.app._update_deadline=datetime.now().timestamp()+10
        self.app._updating=True

    def test_does_not_close_until_helper_prepares_package(self):
        self.app._poll_update_handoff()
        self.app.db.close.assert_not_called()
        self.app.root.destroy.assert_not_called()
        self.app.root.after.assert_called_once()
        self.app._update_handoff.write_text('PREPARED',encoding='utf-8')
        self.app._poll_update_handoff()
        self.app.db.commit.assert_called_once()
        self.app.db.close.assert_called_once()
        self.app.root.destroy.assert_called_once()
        self.assertFalse(self.app._update_handoff.exists())

    def test_installer_exit_does_not_close_app(self):
        self.app._update_worker.poll.return_value=1
        with patch.object(businessdesk.messagebox,'showerror') as error:
            self.app._poll_update_handoff()
        self.app.db.close.assert_not_called()
        self.app.root.destroy.assert_not_called()
        error.assert_called_once()
        self.assertFalse(self.app._updating)

    def test_reports_specific_helper_failure_without_closing(self):
        status={'status':'failed','attempt_id':self.app._update_attempt,'message':'Insufficient disk space'}
        (self.data/'updates'/'install_status.json').write_text(json.dumps(status),encoding='utf-8')
        with patch.object(businessdesk.messagebox,'showerror') as error:
            self.app._poll_update_handoff()
        self.assertIn('Insufficient disk space',error.call_args.args[1])
        self.app.root.destroy.assert_not_called()

if __name__=='__main__':unittest.main()
