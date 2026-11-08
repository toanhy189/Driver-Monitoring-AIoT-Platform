"""Final-account/assignment/privacy acceptance on disposable services only."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session, select
import test_week4_integration as fixtures
from app.core.db import engine
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.video import AiVideo
from app.models.command import Command
from app.services.websocket_manager import ConnectionManager
from app.services.ws_tickets import issue_ticket
from datetime import timedelta


@unittest.skipUnless(os.getenv("W4_INTEGRATION") == "1", "Use the disposable week-4 runner")
class FinalCore(fixtures.Week4Integration):
    def login(self, role="Customer"):
        with Session(engine) as session:
            user = session.get(User, self.users[role])
            user.hash_password = get_password_hash("final-test-password")
            session.add(user); session.commit()
            username = user.username
        response = self.client.post("/api/login", json={"username": username, "password": "final-test-password"})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_blocked_account_revokes_existing_token_and_socket_ticket(self):
        headers = self.login()
        ticket = self.client.post("/api/ws-ticket", headers=headers).json()["ticket"]
        result = self.client.patch(f"/api/users/{self.users['Customer']}", headers=self.auth("Admin"), json={"status":"DISABLED"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 401)
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/telemetry?ticket="+ticket): pass
        self.assertEqual(self.client.post("/api/login", json={"username":result.json()["username"],"password":"final-test-password"}).status_code,401)
        self.client.patch(f"/api/users/{self.users['Customer']}", headers=self.auth("Admin"), json={"status":"ACTIVE"})
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code,401)
        self.login()

    def test_password_and_logout_revoke_tokens(self):
        headers=self.login()
        self.assertEqual(self.client.post("/api/me/password",headers=headers,json={"current_password":"wrong","new_password":"next-final-password"}).status_code,403)
        response=self.client.post("/api/me/password",headers=headers,json={"current_password":"final-test-password","new_password":"next-final-password"})
        self.assertEqual(response.status_code,204,response.text)
        self.assertEqual(self.client.get("/api/me",headers=headers).status_code,401)
        with Session(engine) as session: username=session.get(User,self.users["Customer"]).username
        result=self.client.post("/api/login",json={"username":username,"password":"next-final-password"})
        self.assertEqual(result.status_code,200,result.text)
        headers={"Authorization":"Bearer "+result.json()["access_token"]}
        self.assertEqual(self.client.post("/api/logout",headers=headers).status_code,204)
        self.assertEqual(self.client.get("/api/me",headers=headers).status_code,401)

    def test_profile_update_has_no_role_escalation(self):
        headers=self.login()
        body={"fullname":"Updated User","email":f"profile-{self.suffix}@example.test","phone":"098"+str(self.users["Customer"]).zfill(8)}
        response=self.client.put("/api/me",headers=headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn("hash_password",response.json())
        self.assertEqual(self.client.put("/api/me",headers=headers,json={**body,"role":"Admin"}).status_code,422)

    def test_assignment_is_idempotent_and_revocation_preserves_history(self):
        path=f"/api/users/{self.users['Customer']}/devices/{self.device_id}"
        self.assertEqual(self.client.put(path,headers=self.auth("Customer")).status_code,403)
        for _ in range(2): self.assertEqual(self.client.put(path,headers=self.auth("Admin")).status_code,200)
        self.assertEqual(self.client.get(f"/api/devices/{self.device_id}",headers=self.auth("Customer")).status_code,200)
        self.assertEqual(self.client.delete(path,headers=self.auth("Admin")).status_code,204)
        self.assertEqual(self.client.get(f"/api/devices/{self.device_id}",headers=self.auth("Customer")).status_code,404)
        with Session(engine) as session:
            rows=session.exec(select(UserDevice).where(UserDevice.user_id==self.users['Customer'],UserDevice.device_id==self.device_id)).all()
            self.assertEqual(len(rows),1); self.assertIsNotNone(rows[0].unassigned_at)

    def test_admin_cannot_disable_or_demote_self(self):
        path=f"/api/users/{self.users['Admin']}"
        for body in ({"status":"DISABLED"},{"role":"Customer"}):
            self.assertEqual(self.client.patch(path,headers=self.auth("Admin"),json=body).status_code,409)

    def test_admin_create_roles_and_public_registration_stays_customer(self):
        body={"fullname":"Created test","username":"final-"+self.suffix,"email":"final-"+self.suffix+"@example.test","phone":"097"+str(self.users['Admin']).zfill(8),"password":"final-password","confirm_password":"final-password","role":"Employee"}
        response=self.client.post("/api/users",headers=self.auth("Admin"),json=body)
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['role'],'Employee')
        self.assertEqual(self.client.post("/api/users",headers=self.auth("Customer"),json=body).status_code,403)
        public = {**body, "username": "public-"+self.suffix, "email": "public-"+self.suffix+"@example.test", "phone": "096"+str(self.users['Admin']).zfill(8), "role": "Admin"}
        response = self.client.post('/api/register', json=public)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['user']['role'], 'Customer')

    def test_hardware_metadata_requires_assigned_manager(self):
        path=f'/api/devices/{self.device_id}/hardware'
        body={'hardware_version':'Laptop USB camera - verified label'}
        self.assertEqual(self.client.patch(path,headers=self.auth('Customer'),json=body).status_code,403)
        result=self.client.patch(path,headers=self.auth('Employee'),json=body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['hardware_version'],body['hardware_version'])

    def test_metrics_requires_separate_secret_and_has_real_database_counts(self):
        from app.core.config import settings
        with patch.object(settings,'METRICS_TOKEN','private-metrics-test'):
            self.assertEqual(self.client.get('/metrics').status_code,401)
            self.assertEqual(self.client.get('/metrics',headers=self.auth('Admin')).status_code,401)
            result=self.client.get('/metrics',headers={'Authorization':'Bearer private-metrics-test'})
            self.assertEqual(result.status_code,200,result.text)
            self.assertIn('devices_online ',result.text)
            self.assertNotIn(self.device_code,result.text)

    def test_video_quota_preserves_files_and_deleted_upload_stays_deleted(self):
        from io import BytesIO
        from fastapi import UploadFile, HTTPException
        from starlette.datastructures import Headers
        from tempfile import TemporaryDirectory
        from app.core.config import settings
        from app.models.device import Device
        from app.services.video_storage import store_video
        content=b'\x00\x00\x00\x18ftypisom'+b'0'*32
        def upload(): return UploadFile(BytesIO(content), filename='fixture.mp4', headers=Headers({'content-type':'video/mp4'}))
        with TemporaryDirectory() as directory, patch.object(settings,'AI_VIDEO_DIR',Path(directory)):
            with Session(engine) as session:
                device=session.get(Device,self.device_id)
                with patch.object(settings,'AI_VIDEO_TOTAL_MAX_BYTES',len(content)-1):
                    with self.assertRaises(HTTPException) as error: store_video(session,device,upload(),'ATTENTIVE','quota-'+self.suffix)
                    self.assertEqual(error.exception.status_code,507)
                self.assertEqual(list(Path(directory).iterdir()),[])
                row,created=store_video(session,device,upload(),'ATTENTIVE','manual-'+self.suffix)
                self.assertTrue(created); row_id=row.id
            self.assertEqual(self.client.delete(f'/api/videos/{row_id}',headers=self.auth('Admin')).status_code,204)
            with Session(engine) as session:
                row,created=store_video(session,session.get(Device,self.device_id),upload(),'ATTENTIVE','manual-'+self.suffix)
                self.assertFalse(created); self.assertIsNotNone(row.deleted_at)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_admin_receives_unassigned_realtime_but_customer_does_not(self):
        with Session(engine) as session:
            link=session.exec(select(UserDevice).where(UserDevice.user_id==self.users['Admin'],UserDevice.device_id==self.device_id)).one()
            link.unassigned_at=datetime.now(timezone.utc).replace(tzinfo=None); session.add(link); session.commit()
        sent=[]
        class Socket:
            def __init__(self,role): self.role=role
            async def send_json(self,event): sent.append(self.role)
        manager=ConnectionManager()
        manager.connections={Socket(role):self.users[role] for role in ('Admin','Employee','Customer')}
        asyncio.run(manager.send_to_device_users({'type':'device.updated','data':{'device_id':self.device_id}}))
        self.assertEqual(set(sent),{'Admin','Employee'})

    def test_manual_video_delete_keeps_tombstone_and_authorization(self):
        from tempfile import TemporaryDirectory
        from app.core.config import settings
        with TemporaryDirectory(prefix='final-private-video-') as directory, patch.object(settings,'AI_VIDEO_DIR',Path(directory)):
            row=AiVideo(device_id=self.device_id,message_id='final-video-'+self.suffix,state='ATTENTIVE',storage_key=self.suffix+'.mp4',sha256='0'*64,size_bytes=16)
            with Session(engine) as session:
                session.add(row);session.commit();session.refresh(row);video_id=row.id
            (Path(directory)/row.storage_key).write_bytes(b'private-fixture')
            path=f'/api/videos/{video_id}'
            self.assertEqual(self.client.delete(path,headers=self.auth('Customer')).status_code,403)
            self.assertEqual(self.client.delete(path,headers=self.auth('Employee')).status_code,204)
            self.assertFalse((Path(directory)/row.storage_key).exists())
            with Session(engine) as session: self.assertIsNotNone(session.get(AiVideo,video_id).deleted_at)
            self.assertEqual(self.client.get(path+'/content',headers=self.auth('Admin')).status_code,404)
            response=self.client.get('/api/videos/storage',headers=self.auth('Admin'))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['deletion_policy'],'MANUAL_ONLY')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(FinalCore(name) for name in FinalCore.__dict__ if name.startswith('test_'))
