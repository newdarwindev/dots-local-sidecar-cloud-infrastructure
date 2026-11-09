import hashlib, json, pathlib, tarfile, urllib.request
root = pathlib.Path(__file__).resolve().parents[1]
a = json.loads((root/'artifacts.lock.json').read_text())['artifacts']['helm']
data = urllib.request.urlopen(a['url'], timeout=60).read()
assert hashlib.sha256(data).hexdigest() == a['sha256']
p=pathlib.Path('/tmp/helm.tar.gz'); p.write_bytes(data)
with tarfile.open(p) as tar:
    member=tar.getmember('linux-amd64/helm')
    target=pathlib.Path('/usr/local/bin/helm');target.write_bytes(tar.extractfile(member).read());target.chmod(0o755)
