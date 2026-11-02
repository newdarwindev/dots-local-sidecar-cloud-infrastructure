"""Docker-only chart rendering and safety regression validation; no cluster needed."""
import hashlib, importlib.util, io, json, pathlib, subprocess, tarfile, tempfile, unittest, urllib.request
import yaml
ROOT=pathlib.Path(__file__).resolve().parents[1]
assert pathlib.Path('/.dockerenv').exists(), 'Run only through the committed Docker workflow'
LOCK=json.loads((ROOT/'artifacts.lock.json').read_text())
def read(p): return yaml.safe_load((ROOT/p).read_text())
def docs(text): return [d for d in yaml.safe_load_all(text) if d]
class Configuration(unittest.TestCase):
    def test_vm_exposure_and_resource_budget(self):
        vm=read('lima/primary.yaml')
        self.assertEqual((vm['cpus'],vm['memory'],vm['disk']),(2,'4GiB','40GiB'))
        self.assertEqual(vm['mounts'],[]);self.assertEqual(vm['networks'],[])
        self.assertEqual(vm['ssh']['forwardAgent'],False)
        self.assertEqual([p['hostIP'] for p in vm['portForwards'][:-1]],['127.0.0.1']*3)
        self.assertTrue(vm['portForwards'][-1]['ignore'])
        self.assertTrue(vm['images'][0]['digest'].startswith('sha256:'))
    def test_bootstrap_and_gitops_stay_gated(self):
        k3s=read('k3s/config.yaml');self.assertTrue(k3s['secrets-encryption'])
        self.assertEqual(k3s['write-kubeconfig-mode'],'0600')
        self.assertIn('traefik',k3s['disable']);self.assertIn('servicelb',k3s['disable'])
        for name in ['homarr','openbao']:
            a=read(f'gitops/{name}.yaml');self.assertFalse(a['spec']['syncPolicy']['automated']['enabled'])
            self.assertFalse(a['spec']['syncPolicy']['automated']['prune'])
        p=read('gitops/project.yaml')['spec'];self.assertEqual(p['clusterResourceWhitelist'],[])
        self.assertNotIn('Secret',[x['kind'] for x in p['namespaceResourceWhitelist']])
        self.assertNotIn('*',p['sourceRepos'])
    def test_scoped_credential_delivery(self):
        eso=read('values/external-secrets.yaml');self.assertTrue(eso['scopedRBAC'])
        self.assertEqual(eso['scopedNamespace'],'homarr');self.assertFalse(eso['processClusterStore'])
        bao=read('values/openbao.yaml');self.assertFalse(bao['global']['tlsDisable'])
        self.assertEqual(bao['server']['ha']['replicas'],1)
        self.assertFalse(bao['server']['serviceAccount']['createSecret'])
        self.assertTrue(bao['server']['auditStorage']['enabled'])
        for role in docs((ROOT/'bootstrap/argocd-rbac.yaml').read_text()):
            if role['kind']=='Role':
                for rule in role['rules']:
                    self.assertNotIn('*',rule['verbs']);self.assertNotIn('secrets',rule['resources'])
                    self.assertNotIn('delete',rule['verbs'])
    def test_pinned_charts_render_without_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            for name,ns in [('argocd','argocd'),('openbao','openbao'),('homarr','homarr'),('external-secrets','homarr')]:
                with self.subTest(chart=name):
                    a=LOCK['artifacts'][name];data=urllib.request.urlopen(a['url'],timeout=60).read()
                    self.assertEqual(hashlib.sha256(data).hexdigest(),a['sha256'])
                    p=pathlib.Path(td)/a['filename'];p.write_bytes(data)
                    subprocess.run(['helm','lint',str(p),'-f',str(ROOT/'values'/f'{name}.yaml')],check=True)
                    text=subprocess.check_output(['helm','template',name,str(p),'--namespace',ns,'--kube-version',LOCK['kubernetesVersion'],'--include-crds','--skip-tests','-f',str(ROOT/'values'/f'{name}.yaml')],text=True)
                    rendered=docs(text);self.assertTrue(rendered)
                    for obj in rendered:
                        kind=obj['kind'];spec=obj.get('spec',{})
                        self.assertNotIn(kind,['Ingress','Gateway'])
                        if kind=='Service':self.assertEqual(spec.get('type','ClusterIP'),'ClusterIP')
                        if kind in ['Deployment','StatefulSet','Job']:
                            pod=spec['template']['spec'];self.assertFalse(pod.get('hostNetwork',False))
                            for v in pod.get('volumes',[]):self.assertNotIn('hostPath',v)
                            for c in pod.get('containers',[])+pod.get('initContainers',[]):
                                self.assertNotIn(':latest',c['image']);self.assertIn(':',c['image'])
                        if name=='argocd':self.assertNotIn(kind,['ClusterRole','ClusterRoleBinding'])
                        if name in ['homarr','openbao']:
                            self.assertNotIn(kind,['ClusterRole','ClusterRoleBinding','Secret'])
                    if name=='homarr':
                        self.assertTrue(any(o['kind']=='PersistentVolumeClaim' for o in rendered))
                        self.assertIn('homarr-db-encryption',text)
                    print(f'{name}: {len(rendered)} rendered resources; pinned archive verified')
    def test_installer_rejects_unsafe_archives(self):
        spec=importlib.util.spec_from_file_location('infra',ROOT/'scripts/infra.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            archive=pathlib.Path(td)/'bad.tar'
            with tarfile.open(archive,'w') as tar:
                entry=tarfile.TarInfo('../outside');entry.size=1;tar.addfile(entry,io.BytesIO(b'x'))
            with self.assertRaises(SystemExit):module.unpack(archive,pathlib.Path(td)/'dest')
            self.assertFalse((pathlib.Path(td)/'outside').exists())
    def test_pinned_runtime_archive_is_extractable(self):
        spec=importlib.util.spec_from_file_location('infra',ROOT/'scripts/infra.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        a=LOCK['artifacts']['lima'];data=urllib.request.urlopen(a['url'],timeout=60).read()
        self.assertEqual(hashlib.sha256(data).hexdigest(),a['sha256'])
        with tempfile.TemporaryDirectory() as td:
            archive=pathlib.Path(td)/'lima.tar.gz';archive.write_bytes(data)
            dest=pathlib.Path(td)/'runtime';module.unpack(archive,dest)
            self.assertTrue((dest/'bin/limactl').is_file())
            # Read archive structure only. Never execute the runtime in CI.
    def test_python_scripts_compile(self):
        for p in ROOT.rglob('*.py'):compile(p.read_text(),str(p),'exec')
if __name__=='__main__':unittest.main(verbosity=2)
