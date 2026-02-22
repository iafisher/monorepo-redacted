#!/usr/bin/env bash

set -eux

etc_os_release=/etc/os-release
if ! grep 'NAME="Rocky Linux"' "$etc_os_release" &> /dev/null; then
  echo "fatal: not on a Rocky Linux machine according to $etc_os_release"
  exit 1
fi

newuser=iafisher
echo "==> creating user '$newuser' and giving sudo access"
adduser $newuser
usermod -a -G systemd-journal $newuser
mkdir -p /home/$newuser/.ssh
chmod 700 /home/$newuser/.ssh
# /root/authorized_keys was previously scp'ed outside of this script
mv /root/authorized_keys /home/$newuser/.ssh/
chmod 600 /home/$newuser/.ssh/authorized_keys
chown -R $newuser:$newuser /home/$newuser/.ssh
restorecon -R /home/iafisher/.ssh

sudoers_d=/etc/sudoers.d
if ! [[ -d "$sudoers_d" ]]; then
  echo "fatal: $sudoers_d does not exist"
  exit 1
fi

echo "$newuser ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/$newuser
chmod 0440 /etc/sudoers.d/$newuser
