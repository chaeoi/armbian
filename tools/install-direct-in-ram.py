#!/usr/bin/env python3
"""Install the single Armbian OS from a verified RAM root. Erases old OS areas."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback

STAGE = Path('/opt/ec6108-install')
STATUS = Path('/run/ec6108-flash-status.json')
spec = importlib.util.spec_from_file_location('prepare',STAGE/'prepare-install.py')
prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
manifest = json.loads((STAGE/'manifest.json').read_text())
def status(phase, **extra):
    result = {'phase':phase,**extra}
    STATUS.write_text(json.dumps(result)+'\n');print(json.dumps(result),flush=True)
def run(*args, timeout=180):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout).strip()

loop = None
mounted = False
try:
    assert Path('/etc/ec6108-ram-mode').exists(), 'RAM marker required'
    assert run('findmnt','-n','-o','FSTYPE','/') == 'tmpfs', 'Must run from RAM'
    assert os.uname().release == manifest['kernel_release']
    cid = prepare.hardware(manifest)
    image = (STAGE/'uImage').read_bytes();prepare.validate_image(image,manifest)
    if subprocess.run(['mountpoint','-q','/.oldroot']).returncode == 0:
        run('umount','/.oldroot')
    for i in range(1,10):
        assert subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p'+str(i)],
                              stdout=subprocess.DEVNULL).returncode == 1, 'Old OS still mounted'
    root_bytes = manifest['emmc_bytes']-prepare.ROOT_OFFSET
    status('formatting-single-root',root_bytes=root_bytes)
    loop = run('losetup','--find','--show','--offset',str(prepare.ROOT_OFFSET),
               '--sizelimit',str(root_bytes),'/dev/mmcblk0')
    run('mkfs.ext4','-q','-F','-m','0','-L','armbian-root','-U',manifest['root_uuid'],
        '-E','nodiscard,lazy_itable_init=0,lazy_journal_init=0',loop,timeout=180)
    target = Path('/run/ec6108-newroot');target.mkdir(exist_ok=True)
    run('mount','-t','ext4',loop,str(target));mounted=True
    status('copying-armbian')
    excludes = ['.oldroot','.hinas','opt/ec6108-install','etc/ec6108-ram-mode','etc/fstab',
                'run/*','proc/*','sys/*','dev/*','tmp/*','mnt/*','var/log/*','var/cache/*']
    command = ['tar','--numeric-owner','--xattrs','--acls','--one-file-system','--sparse']
    command += ['--exclude=./'+x for x in excludes]
    source = subprocess.Popen(command+['-C','/','-cpf','-','.'],stdout=subprocess.PIPE)
    extracted = subprocess.run(['tar','--numeric-owner','--xattrs','--acls','-xpf','-',
                                '-C',str(target)],stdin=source.stdout,timeout=180)
    source.stdout.close()
    assert source.wait(timeout=30) == 0 and extracted.returncode == 0, 'Root copy failed'
    shutil.copy2(STAGE/'fstab.target',target/'etc/fstab')
    env = prepare.environment(prepare.read_environment(),'/dev/mmcblk0p3')
    config = {'kernel_release':manifest['kernel_release'],'kernel_bytes':manifest['kernel_bytes'],
              'kernel_sha256':manifest['kernel_sha256'],'root_uuid':manifest['root_uuid'],
              'root_offset':prepare.ROOT_OFFSET,'emmc_cid':cid,
              'environment_sha256':hashlib.sha256(env).hexdigest(),'installation':'single-armbian-direct-emmc'}
    (target/'etc/ec6108-system.json').write_text(json.dumps(config,indent=2)+'\n')
    release = target/'usr/share/ec6108v9';release.mkdir(parents=True,exist_ok=True)
    (release/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert (target/'sbin/init').exists() and (target/'usr/local/sbin/ec6108-verify-system').exists()
    assert not (target/'.hinas').exists() and not (target/'var/lib/armbian-port/rootfs.img').exists()
    os.sync();run('umount',str(target));mounted=False
    status('checking-root-filesystem')
    checked = subprocess.run(['e2fsck','-fn',loop],capture_output=True,text=True,timeout=180)
    assert checked.returncode == 0, checked.stdout+checked.stderr
    run('losetup','-d',loop);loop=None
    prepare.write_kernel(image,manifest)
    prepare.write_environment(env)
    os.sync()
    status('ready-to-reboot',root_bytes=root_bytes,emmc_cid=cid,fsck=checked.stdout+checked.stderr)
except BaseException as error:
    status('failed',error=str(error),traceback=traceback.format_exc())
    raise
finally:
    if mounted:
        subprocess.run(['umount','/run/ec6108-newroot'])
    if loop:
        subprocess.run(['losetup','-d',loop])
