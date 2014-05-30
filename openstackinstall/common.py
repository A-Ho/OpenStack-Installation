import fcntl
import os
import socket
import struct
import subprocess
import sys
import time

from datetime import datetime


# These will be lazy-loaded once python dependencies are on the system
iniparse = None
psutil = None


#######################################################################
def base_system_update():
  print ''
  log('Updating and Upgrading System')
  run_command("apt-get clean" , True)
  run_command("apt-get autoclean -y" , True)
  run_command("apt-get update -y" , True)
  run_command("apt-get install -y ubuntu-cloud-keyring python-setuptools python-iniparse python-psutil python-software-properties", True)
  delete_file("/etc/apt/sources.list.d/icehouse.list")
  run_command("echo deb http://ubuntu-cloud.archive.canonical.com/ubuntu precise-updates/icehouse main >> /etc/apt/sources.list.d/icehouse.list")
  run_command("apt-get update -y", True)
  run_command("apt-get dist-upgrade -y", True)
  run_command("apt-get install -y linux-image-generic-lts-saucy linux-headers-generic-lts-saucy", True)
#######################################################################


#######################################################################
def delete_file(filePath):
  if os.path.exists(filePath) and os.path.isfile(filePath):
    os.remove(filePath)
#######################################################################


#######################################################################
def get_config_ini(filePath, section, key):
  if not os.path.exists(filePath):
    raise Exception("Unable to get config value from INI, file " + str(filePath) + " does not exist")
  if not os.path.isfile(filePath):
    raise Exception("Unable to get config value from INI, path " + str(filePath) + " is not a file")
  global iniparse
  if iniparse is None:
    iniparse = __import__('iniparse')
  config = iniparse.ConfigParser()
  config.readfp(open(filePath))
  return config.get(section, key)
#######################################################################


#######################################################################
def get_network_address(interfaceName):
  if not interfaceName or len(str(interfaceName)) == 0:
    raise Exception("Unable to get network address, no interface name specified")
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', interfaceName[:15]))[20:24])
  except:
    raise Exception("Unable to get network address for interface " + str(interfaceName))
#######################################################################


#######################################################################
def install_cinder(databaseUserPassword, mySQLIP, mySQLPassword, controlNodeIP, apiIP):
  if not databaseUserPassword or len(str(databaseUserPassword)) == 0:
    raise Exception("Unable to install/configure cinder, no database user password specified")
  if not mySQLIP or len(str(mySQLIP)) == 0:
    raise Exception("Unable to install/configure cinder, no MySQL IP specified")
  if not mySQLPassword or len(str(mySQLPassword)) == 0:
    raise Exception("Unable to install/configure cinder, no MySQL Password specified")
  if not controlNodeIP or len(str(controlNodeIP)) == 0:
    raise Exception("Unable to install/configure cinder, no control node IP specified")
  if not apiIP or len(str(apiIP)) == 0:
    raise Exception("Unable to install/configure cinder, no API IP specified")
  print ''
  log('Installing Cinder')
  run_db_command(mySQLPassword, "CREATE DATABASE IF NOT EXISTS cinder CHARACTER SET utf8 COLLATE utf8_general_ci;")
  run_db_command(mySQLPassword, "GRANT ALL ON cinder.* TO 'cinder'@'%' IDENTIFIED BY '" + databaseUserPassword + "';")
  delete_file('/etc/apt/sources.list.d/icehouse-iscsitarget.list')
  run_command("echo deb http://ppa.launchpad.net/smb/iscsitarget/ubuntu precise main >> /etc/apt/sources.list.d/icehouse-iscsitarget.list")
  run_command("echo deb-src http://ppa.launchpad.net/smb/iscsitarget/ubuntu precise main >> /etc/apt/sources.list.d/icehouse-iscsitarget.list")
  os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
  run_command("apt-get update -y", True)
  try:
    run_command("apt-get install -y --force-yes iscsitarget open-iscsi iscsitarget-dkms", True)
  except:
    # try one last time
    run_command("apt-get install -y --force-yes iscsitarget open-iscsi iscsitarget-dkms", True)
  run_command("apt-get install -y cinder-api cinder-scheduler cinder-volume" , True)
  log('Configuring Cinder')
  run_command("sed -i 's/false/true/g' /etc/default/iscsitarget")
  run_command("service iscsitarget restart")
  run_command("service open-iscsi restart")
  cinderConf = '/etc/cinder/cinder.conf'
  set_config_ini(cinderConf, 'DEFAULT', 'rootwrap_config', '/etc/cinder/rootwrap.conf')
  set_config_ini(cinderConf, 'DEFAULT', 'sql_connection', "mysql://cinder:%s@%s/cinder" %(databaseUserPassword,mySQLIP))
  set_config_ini(cinderConf, 'DEFAULT', 'api_paste_config', '/etc/cinder/api-paste.ini')
  set_config_ini(cinderConf, 'DEFAULT', 'iscsi_helper', 'ietadm')
  set_config_ini(cinderConf, 'DEFAULT', 'volume_name_template', 'volume-%s')
  set_config_ini(cinderConf, 'DEFAULT', 'volume_group', 'cinder-volumes')
  set_config_ini(cinderConf, 'DEFAULT', 'verbose', 'False')
  set_config_ini(cinderConf, 'DEFAULT', 'auth_strategy', 'keystone')
  set_config_ini(cinderConf, 'DEFAULT', 'iscsi_ip_address', controlNodeIP)
  set_config_ini(cinderConf, 'DEFAULT', 'rpc_backend', 'cinder.openstack.common.rpc.impl_kombu')
  set_config_ini(cinderConf, 'DEFAULT', 'rabbit_host', controlNodeIP)
  set_config_ini(cinderConf, 'DEFAULT', 'rabbit_port', '5672')
  cinderApiPasteConf = '/etc/cinder/api-paste.ini'
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'service_protocol', 'http')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'service_host', apiIP)
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'service_port', '5000')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'auth_host', controlNodeIP)
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'auth_port', '35357')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'auth_protocol', 'http')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'admin_tenant_name', 'service')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'admin_user', 'cinder')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'admin_password', 'cinder')
  set_config_ini(cinderApiPasteConf, 'filter:authtoken', 'signing_dir', '/var/lib/cinder')
  run_command("cinder-manage db sync", True)
  run_command("cd /etc/init.d/; for i in $( ls cinder-* ); do service $i restart; done", True)
  log('Completed Cinder')
#######################################################################


#######################################################################
def install_glance(databaseUserPassword, mySQLIP, mySQLPassword, controlNodeIP):
  if not databaseUserPassword or len(str(databaseUserPassword)) == 0:
    raise Exception("Unable to install/configure glance, no database user password specified")
  if not mySQLIP or len(str(mySQLIP)) == 0:
    raise Exception("Unable to install/configure glance, no MySQL IP specified")
  if not mySQLPassword or len(str(mySQLPassword)) == 0:
    raise Exception("Unable to install/configure glance, no MySQL Password specified")
  if not controlNodeIP or len(str(controlNodeIP)) == 0:
    raise Exception("Unable to install/configure glance, no control node IP specified")
  print ''
  log('Installing Glance')
  run_db_command(mySQLPassword, "CREATE DATABASE IF NOT EXISTS glance CHARACTER SET utf8 COLLATE utf8_general_ci;")
  run_db_command(mySQLPassword, "GRANT ALL ON glance.* TO 'glance'@'%' IDENTIFIED BY '" + databaseUserPassword + "';")
  run_command("apt-get install -y glance" , True)
  log('Configuring Glance')
  glanceApiConf = '/etc/glance/glance-api.conf'
  set_config_ini(glanceApiConf, 'DEFAULT', 'sql_connection', "mysql://glance:%s@%s/glance" %(databaseUserPassword,mySQLIP))
  set_config_ini(glanceApiConf, 'DEFAULT', 'verbose', 'false')
  set_config_ini(glanceApiConf, 'DEFAULT', 'debug', 'false')
  #set_config_ini(glanceApiConf, 'DEFAULT', 'db_enforce_mysql_charset', 'false')
  set_config_ini(glanceApiConf, 'paste_deploy', 'flavor', 'keystone')
  glanceApiPasteConf = '/etc/glance/glance-api-paste.ini'
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'auth_host', controlNodeIP)
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'auth_port', '35357')
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'auth_protocol', 'http')
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'admin_tenant_name', 'service')
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'admin_user', 'glance')
  set_config_ini(glanceApiPasteConf, 'filter:authtoken', 'admin_password', 'glance')
  glanceRegistryConf = '/etc/glance/glance-registry.conf'
  set_config_ini(glanceRegistryConf, 'DEFAULT', 'sql_connection', "mysql://glance:%s@%s/glance" %(databaseUserPassword,mySQLIP))
  set_config_ini(glanceRegistryConf, 'DEFAULT', 'verbose', 'false')
  set_config_ini(glanceRegistryConf, 'DEFAULT', 'debug', 'false')
  set_config_ini(glanceRegistryConf, 'paste_deploy', 'flavor', 'keystone')
  glanceRegistryPasteConf = '/etc/glance/glance-registry-paste.ini'
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'auth_host', controlNodeIP)
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'auth_port', '35357')
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'auth_protocol', 'http')
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'admin_tenant_name', 'service')
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'admin_user', 'glance')
  set_config_ini(glanceRegistryPasteConf, 'filter:authtoken', 'admin_password', 'glance')
  run_command("service glance-api restart", True)
  run_command("service glance-registry restart", True)
  time.sleep(10)
  run_command("glance-manage db_sync", True)
  log('Completed Glance')
#######################################################################


#######################################################################
def install_horizon():
  print ''
  log('Installing Horizon')
  run_command("apt-get install -y openstack-dashboard memcached", True)
  run_command("service apache2 restart", True)
  run_command("service memcached restart", True)
  log('Completed Horizon')
#######################################################################


#######################################################################
def install_keystone(databaseUserPassword, mySQLIP, mySQLPassword, controlNodeIP, apiIP):
  if not databaseUserPassword or len(str(databaseUserPassword)) == 0:
    raise Exception("Unable to install/configure keystone, no database user password specified")
  if not mySQLIP or len(str(mySQLIP)) == 0:
    raise Exception("Unable to install/configure keystone, no MySQL IP specified")
  if not mySQLPassword or len(str(mySQLPassword)) == 0:
    raise Exception("Unable to install/configure keystone, no MySQL Password specified")
  if not controlNodeIP or len(str(controlNodeIP)) == 0:
    raise Exception("Unable to install/configure keystone, no control node IP specified")
  if not apiIP or len(str(apiIP)) == 0:
    raise Exception("Unable to install/configure keystone, no API IP specified")
  print ''
  log('Installing Keystone')
  run_db_command(mySQLPassword, "CREATE DATABASE IF NOT EXISTS keystone CHARACTER SET utf8 COLLATE utf8_general_ci;")
  run_db_command(mySQLPassword, "GRANT ALL ON keystone.* TO 'keystone'@'%' IDENTIFIED BY '" + databaseUserPassword + "';")
  run_command("apt-get install -y python-six python-babel keystone" , True)
  log('Configuring Keystone')
  keystoneConf = '/etc/keystone/keystone.conf'
  set_config_ini(keystoneConf, 'DEFAULT', 'admin_token', 'ADMINTOKEN')
  set_config_ini(keystoneConf, 'DEFAULT', 'admin_port', 35357)
  set_config_ini(keystoneConf, 'DEFAULT', 'log_dir', '/var/log/keystone')
  set_config_ini(keystoneConf, 'database', 'connection', "mysql://keystone:%s@%s/keystone" %(databaseUserPassword,mySQLIP))
  set_config_ini(keystoneConf, 'signing', 'token_format', 'UUID')
  run_command("service keystone restart" , True)
  time.sleep(10)
  run_command("keystone-manage db_sync" , True)

  # Configure users/endpoints/etc
  os.environ['SERVICE_TOKEN'] = 'ADMINTOKEN'
  os.environ['SERVICE_ENDPOINT'] = 'http://%s:35357/v2.0'% controlNodeIP
  os.environ['no_proxy'] = "localhost,127.0.0.1,%s,%s" % (controlNodeIP,apiIP)

  # Little bit of dancing to handle if the admin user already exists or maybe does not yet
  adminrc = '/root/openstack-admin.rc'
  adminAuthArg = ''
  adminUserExists = os.path.exists(adminrc) and os.path.isfile(adminrc)
  if adminUserExists:
    adminAuthArg = " --os-username admin --os-password secret --os-auth-url http://%s:5000/v2.0 " %apiIP

  admin_tenant = run_command("keystone " + adminAuthArg + " tenant-list | grep admin | awk '{print $2}'")
  if not admin_tenant or not len(str(admin_tenant)) > 0:
    admin_tenant = run_command("keystone " + adminAuthArg + " tenant-create --name admin --description 'Admin Tenant' --enabled true |grep ' id '|awk '{print $4}'")

  admin_user = run_command("keystone " + adminAuthArg + " user-list | grep admin | awk '{print $2}'")
  if not admin_user or not len(str(admin_user)) > 0:
    admin_user = run_command("keystone " + adminAuthArg + " user-create --tenant_id %s --name admin --pass secret --enabled true|grep ' id '|awk '{print $4}'" % admin_tenant)

  # Now that the admin user definitely exists, setup auth for remaining commands
  run_command("echo 'export OS_USERNAME=admin' >%s" %adminrc)
  run_command("echo 'export OS_PASSWORD=secret' >>%s" %adminrc)
  run_command("echo 'export OS_TENANT_NAME=admin' >>%s" %adminrc)
  run_command("echo 'export OS_AUTH_URL=http://%s:5000/v2.0' >>%s" % (apiIP,adminrc))
  adminAuthArg = " --os-username admin --os-password secret --os-auth-url http://%s:5000/v2.0 " %apiIP

  admin_role = run_command("keystone " + adminAuthArg + " role-list| grep admin | awk '{print $2}'")
  if not admin_role or not len(str(admin_user)) > 0:
    admin_role = run_command("keystone " + adminAuthArg + " role-create --name admin|grep ' id '|awk '{print $4}'")

  admin_role_mapped = run_command("keystone " + adminAuthArg + " user-role-list --user_id %s --tenant_id %s | grep %s | awk '{print $2}'" % (admin_user,admin_tenant,admin_role))
  if not admin_role_mapped or not len(str(admin_role_mapped)) > 0:
    run_command("keystone " + adminAuthArg + " user-role-add --user_id %s --tenant_id %s --role_id %s" % (admin_user, admin_tenant, admin_role))

  service_tenant = run_command("keystone " + adminAuthArg + " tenant-list | grep service | awk '{print $2}'")
  if not service_tenant or not len(str(service_tenant)) > 0:
    service_tenant = run_command("keystone " + adminAuthArg + " tenant-create --name service --description 'Service Tenant' --enabled true |grep ' id '|awk '{print $4}'")

  keystone_service = run_command("keystone " + adminAuthArg + " service-list| grep keystone | awk '{print $2}'")
  if not keystone_service or not len(str(keystone_service)) > 0:
    keystone_service = run_command("keystone " + adminAuthArg + " service-create --name=keystone --type=identity --description='Keystone Identity Service'|grep ' id '|awk '{print $4}'")

  keystone_endpoint = run_command("keystone " + adminAuthArg + " endpoint-list | grep %s | awk '{print $2}'" % keystone_service)
  if keystone_endpoint and len(str(keystone_endpoint)) > 0:
    run_command("keystone " + adminAuthArg + " endpoint-delete %s" % keystone_service)
  run_command("keystone " + adminAuthArg + " endpoint-create --region region --service_id=%s --publicurl=http://%s:5000/v2.0 --internalurl=http://%s:5000/v2.0 --adminurl=http://%s:35357/v2.0" % (keystone_service,apiIP,controlNodeIP,controlNodeIP))

  glance_user = run_command("keystone " + adminAuthArg + " user-list | grep glance | awk '{print $2}'")
  if not glance_user or not len(str(glance_user)) > 0:
    glance_user = run_command("keystone " + adminAuthArg + " user-create --tenant_id %s --name glance --pass glance --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)

  glance_role_mapped = run_command("keystone " + adminAuthArg + " user-role-list --user_id %s --tenant_id %s | grep %s | awk '{print $2}'" % (glance_user, service_tenant, admin_role))
  if not glance_role_mapped or not len(str(glance_role_mapped)) > 0:
    run_command("keystone " + adminAuthArg + " user-role-add --user_id %s --tenant_id %s --role_id %s" % (glance_user, service_tenant, admin_role))

  glance_service = run_command("keystone " + adminAuthArg + " service-list| grep glance | awk '{print $2}'")
  if not glance_service or not len(str(glance_service)) > 0:
    glance_service = run_command("keystone " + adminAuthArg + " service-create --name=glance --type=image --description='Glance Image Service'|grep ' id '|awk '{print $4}'")

  glance_endpoint = run_command("keystone " + adminAuthArg + " endpoint-list | grep %s | awk '{print $2}'" % glance_service)
  if glance_endpoint and len(str(glance_endpoint)) > 0:
    run_command("keystone " + adminAuthArg + " endpoint-delete %s" % glance_service)
  run_command("keystone " + adminAuthArg + " endpoint-create --region region --service_id=%s --publicurl=http://%s:9292/v2 --internalurl=http://%s:9292/v2 --adminurl=http://%s:9292/v2" % (glance_service,apiIP,controlNodeIP,controlNodeIP))

  nova_user = run_command("keystone " + adminAuthArg + " user-list | grep nova | awk '{print $2}'")
  if not nova_user or not len(str(nova_user)) > 0:
    nova_user = run_command("keystone " + adminAuthArg + " user-create --tenant_id %s --name nova --pass nova --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)

  nova_role_mapped = run_command("keystone " + adminAuthArg + " user-role-list --user_id %s --tenant_id %s | grep %s | awk '{print $2}'" % (nova_user, service_tenant, admin_role))
  if not nova_role_mapped or not len(str(nova_role_mapped)) > 0:
    run_command("keystone " + adminAuthArg + " user-role-add --user_id %s --tenant_id %s --role_id %s" % (nova_user, service_tenant, admin_role))

  nova_service = run_command("keystone " + adminAuthArg + " service-list| grep nova | awk '{print $2}'")
  if not nova_service or not len(str(nova_service)) > 0:
    nova_service = run_command("keystone " + adminAuthArg + " service-create --name=nova --type=compute --description='Nova Compute Service'|grep ' id '|awk '{print $4}'")

  nova_endpoint = run_command("keystone " + adminAuthArg + " endpoint-list | grep %s | awk '{print $2}'" % nova_service)
  if nova_endpoint and len(str(nova_endpoint)) > 0:
    run_command("keystone " + adminAuthArg + " endpoint-delete %s" % nova_service)
  run_command("keystone " + adminAuthArg + " endpoint-create --region region --service_id=%s --publicurl='http://%s:8774/v2/$(tenant_id)s' --internalurl='http://%s:8774/v2/$(tenant_id)s' --adminurl='http://%s:8774/v2/$(tenant_id)s'" % (nova_service,apiIP,controlNodeIP,controlNodeIP))

  neutron_user = run_command("keystone " + adminAuthArg + " user-list | grep neutron | awk '{print $2}'")
  if not neutron_user or not len(str(neutron_user)) > 0:
    neutron_user = run_command("keystone " + adminAuthArg + " user-create --tenant_id %s --name neutron --pass neutron --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)

  neutron_role_mapped = run_command("keystone " + adminAuthArg + " user-role-list --user_id %s --tenant_id %s | grep %s | awk '{print $2}'" % (neutron_user, service_tenant, admin_role))
  if not neutron_role_mapped or not len(str(neutron_role_mapped)) > 0:
    run_command("keystone " + adminAuthArg + " user-role-add --user_id %s --tenant_id %s --role_id %s" % (neutron_user, service_tenant, admin_role))

  neutron_service = run_command("keystone " + adminAuthArg + " service-list| grep neutron | awk '{print $2}'")
  if not neutron_service or not len(str(neutron_service)) > 0:
    neutron_service = run_command("keystone " + adminAuthArg + " service-create --name=neutron --type=network  --description='Neutron Networking Service'|grep ' id '|awk '{print $4}'")

  neutron_endpoint = run_command("keystone " + adminAuthArg + " endpoint-list | grep %s | awk '{print $2}'" % neutron_service)
  if neutron_endpoint and len(str(neutron_endpoint)) > 0:
    run_command("keystone " + adminAuthArg + " endpoint-delete %s" % neutron_service)
  run_command("keystone " + adminAuthArg + " endpoint-create --region region --service_id=%s --publicurl=http://%s:9696/ --internalurl=http://%s:9696/ --adminurl=http://%s:9696/" % (neutron_service,apiIP,controlNodeIP,controlNodeIP))

  cinder_user = run_command("keystone " + adminAuthArg + " user-list| grep cinder | awk '{print $2}'")
  if not cinder_user or not len(str(cinder_user)) > 0:
    cinder_user = run_command("keystone " + adminAuthArg + " user-create --tenant_id %s --name cinder --pass cinder --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)

  cinder_role_mapped = run_command("keystone " + adminAuthArg + " user-role-list --user_id %s --tenant_id %s | grep %s | awk '{print $2}'" % (cinder_user, service_tenant, admin_role))
  if not cinder_role_mapped or not len(str(cinder_role_mapped)) > 0:
    run_command("keystone " + adminAuthArg + " user-role-add --user_id %s --tenant_id %s --role_id %s" % (cinder_user, service_tenant, admin_role))

  cinder_service = run_command("keystone " + adminAuthArg + " service-list| grep cinder | awk '{print $2}'")
  if not cinder_service  or not len(str(cinder_service)) > 0:
    cinder_service = run_command("keystone " + adminAuthArg + " service-create --name=cinder --type=volume --description='Cinder Volume Service'|grep ' id '|awk '{print $4}'")

  cinder_endpoint = run_command("keystone " + adminAuthArg + " endpoint-list | grep %s | awk '{print $2}'" % cinder_service)
  if cinder_endpoint and len(str(cinder_endpoint)) > 0:
    run_command("keystone " + adminAuthArg + " endpoint-delete %s" % cinder_service)
  run_command("keystone " + adminAuthArg + " endpoint-create --region region --service_id=%s --publicurl 'http://%s:8776/v1/$(tenant_id)s' --internalurl='http://%s:8776/v1/$(tenant_id)s' --adminurl='http://%s:8776/v1/$(tenant_id)s'" % (cinder_service,apiIP,controlNodeIP,controlNodeIP))

  log('Completed Keystone')
#######################################################################


#######################################################################
def install_mysql(rootPassword):
  if not rootPassword or len(str(rootPassword)) == 0:
    raise Exception("Unable to install/configure MySQL, no root password specified")
  print ''
  log('Installing MySQL')
  os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
  run_command("apt-get install -y mysql-server python-mysqldb" , True)
  log('Configuring MySQL')
  run_command("sed -i 's/127.0.0.1/0.0.0.0/g' /etc/mysql/my.cnf")
  run_command("service mysql restart", True)
  time.sleep(10)
  try:
    run_command("mysqladmin -u root password %s" %rootPassword)
  except:
    # password may already be set, pass
    pass
  # verify database connectivity
  run_db_command(rootPassword, 'show databases;')
  log('Completed MySQL')
#######################################################################


#######################################################################
def install_neutron(databaseUserPassword, mySQLIP, mySQLPassword, controlNodeIP):
  if not databaseUserPassword or len(str(databaseUserPassword)) == 0:
    raise Exception("Unable to install/configure neutron, no database user password specified")
  if not mySQLIP or len(str(mySQLIP)) == 0:
    raise Exception("Unable to install/configure neutron, no MySQL IP specified")
  if not mySQLPassword or len(str(mySQLPassword)) == 0:
    raise Exception("Unable to install/configure neutron, no MySQL Password specified")
  if not controlNodeIP or len(str(controlNodeIP)) == 0:
    raise Exception("Unable to install/configure neutron, no control node IP specified")
  print ''
  log('Installing Neutron')
  run_db_command(mySQLPassword, "CREATE DATABASE IF NOT EXISTS neutron CHARACTER SET utf8 COLLATE utf8_general_ci;")
  run_db_command(mySQLPassword, "GRANT ALL ON neutron.* TO 'neutron'@'%' IDENTIFIED BY '" + databaseUserPassword + "';")
  run_command("apt-get install -y neutron-server" , True)
  run_command("apt-get install -y neutron-plugin-ml2" , True)
  log('Configuring Neutron')
  service_tenant = run_command("keystone tenant-list | grep service | awk '{print $2}'")
  neutronConf = '/etc/neutron/neutron.conf'
  set_config_ini(neutronConf, 'DEFAULT', 'core_plugin', 'neutron.plugins.ml2.plugin.Ml2Plugin')
  set_config_ini(neutronConf, 'DEFAULT', 'service_plugins', 'neutron.services.l3_router.l3_router_plugin.L3RouterPlugin')
  set_config_ini(neutronConf, 'DEFAULT', 'verbose', 'False')
  set_config_ini(neutronConf, 'DEFAULT', 'debug', 'False')
  set_config_ini(neutronConf, 'DEFAULT', 'auth_strategy', 'keystone')
  set_config_ini(neutronConf, 'DEFAULT', 'rabbit_host', controlNodeIP)
  set_config_ini(neutronConf, 'DEFAULT', 'rabbit_port', '5672')
  set_config_ini(neutronConf, 'DEFAULT', 'allow_overlapping_ips', 'False')
  set_config_ini(neutronConf, 'DEFAULT', 'root_helper', 'sudo neutron-rootwrap /etc/neutron/rootwrap.conf')
  set_config_ini(neutronConf, 'DEFAULT', 'notify_nova_on_port_status_changes', 'True')
  set_config_ini(neutronConf, 'DEFAULT', 'notify_nova_on_port_data_changes', 'True')
  set_config_ini(neutronConf, 'DEFAULT', 'nova_url', "http://" + controlNodeIP + ":8774/v2")
  set_config_ini(neutronConf, 'DEFAULT', 'nova_admin_username', 'nova')
  set_config_ini(neutronConf, 'DEFAULT', 'nova_admin_password', 'nova')
  set_config_ini(neutronConf, 'DEFAULT', 'nova_admin_tenant_id', service_tenant)
  set_config_ini(neutronConf, 'DEFAULT', 'nova_admin_auth_url', "http://" + controlNodeIP + ":5000/v2.0/")
  set_config_ini(neutronConf, 'database', 'connection', "mysql://neutron:%s@%s/neutron" %(databaseUserPassword,mySQLIP))
  neutronPasteConf = '/etc/neutron/api-paste.ini'
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'auth_host', controlNodeIP)
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'auth_port', '35357')
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'auth_protocol', 'http')
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'admin_tenant_name', 'service')
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'admin_user', 'neutron')
  set_config_ini(neutronPasteConf, 'filter:authtoken', 'admin_password', 'neutron')
  neutronPluginConf = '/etc/neutron/plugins/ml2/ml2_conf.ini'
  set_config_ini(neutronPluginConf, 'ml2', 'type_drivers', 'vlan,vxlan')
  set_config_ini(neutronPluginConf, 'ml2', 'tenant_network_types', 'vlan,vxlan')
  set_config_ini(neutronPluginConf, 'ml2', 'mechanism_drivers', 'openvswitch,linuxbridge')
  set_config_ini(neutronPluginConf, 'ml2_type_vlan', 'network_vlan_ranges', 'physnet1:2000:2999')
  set_config_ini(neutronPluginConf, 'ml2_type_vxlan', 'vni_ranges', '500:999')
  set_config_ini(neutronPluginConf, 'securitygroup', 'firewall_driver', 'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver')
  run_command("service neutron-server restart", True)
  log('Completed Neutron')
#######################################################################


#######################################################################
def install_nova(databaseUserPassword, mySQLIP, mySQLPassword, controlNodeIP, apiIP):
  if not databaseUserPassword or len(str(databaseUserPassword)) == 0:
    raise Exception("Unable to install/configure nova, no database user password specified")
  if not mySQLIP or len(str(mySQLIP)) == 0:
    raise Exception("Unable to install/configure nova, no MySQL IP specified")
  if not mySQLPassword or len(str(mySQLPassword)) == 0:
    raise Exception("Unable to install/configure nova, no MySQL Password specified")
  if not controlNodeIP or len(str(controlNodeIP)) == 0:
    raise Exception("Unable to install/configure nova, no control node IP specified")
  if not apiIP or len(str(apiIP)) == 0:
    raise Exception("Unable to install/configure nova, no API IP specified")
  print ''
  log('Installing Nova')
  run_db_command(mySQLPassword, "CREATE DATABASE IF NOT EXISTS nova CHARACTER SET utf8 COLLATE utf8_general_ci;")
  run_db_command(mySQLPassword, "GRANT ALL ON nova.* TO 'nova'@'%' IDENTIFIED BY '" + databaseUserPassword + "';")
  run_command("apt-get install -y nova-api nova-cert nova-scheduler nova-conductor novnc nova-consoleauth nova-novncproxy" , True)
  log('Configuring Nova')
  novaConf = '/etc/nova/nova.conf'
  set_config_ini(novaConf, 'DEFAULT', 'logdir', '/var/log/nova')
  set_config_ini(novaConf, 'DEFAULT', 'lock_path', '/var/lib/nova')
  set_config_ini(novaConf, 'DEFAULT', 'root_helper', 'sudo nova-rootwrap /etc/nova/rootwrap.conf')
  set_config_ini(novaConf, 'DEFAULT', 'verbose', 'False')
  set_config_ini(novaConf, 'DEFAULT', 'debug', 'False')
  set_config_ini(novaConf, 'DEFAULT', 'rabbit_host', controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'rpc_backend', 'nova.rpc.impl_kombu')
  set_config_ini(novaConf, 'DEFAULT', 'sql_connection', "mysql://nova:%s@%s/nova" %(databaseUserPassword,mySQLIP))
  set_config_ini(novaConf, 'DEFAULT', 'glance_api_servers', "%s:9292" %controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'image_service', 'nova.image.glance.GlanceImageService')
  set_config_ini(novaConf, 'DEFAULT', 'dhcpbridge_flagfile', '/etc/nova/nova.conf')
  set_config_ini(novaConf, 'DEFAULT', 'auth_strategy', 'keystone')
  set_config_ini(novaConf, 'DEFAULT', 'novnc_enabled', 'true')
  set_config_ini(novaConf, 'DEFAULT', 'nova_url', "http://%s:8774/v2/" %controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'novncproxy_base_url', "http://%s:6080/vnc_auto.html" %apiIP)
  set_config_ini(novaConf, 'DEFAULT', 'vncserver_proxyclient_address', controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'novncproxy_port', '6080')
  set_config_ini(novaConf, 'DEFAULT', 'vncserver_listen', '0.0.0.0')
  set_config_ini(novaConf, 'DEFAULT', 'network_api_class', 'nova.network.neutronv2.api.API')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_admin_username', 'neutron')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_admin_password', 'neutron')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_admin_tenant_name', 'service')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_admin_auth_url', "http://%s:35357/v2.0/" %controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'neutron_auth_strategy', 'keystone')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_url', "http://%s:9696/" %controlNodeIP)
  set_config_ini(novaConf, 'DEFAULT', 'firewall_driver', 'nova.virt.firewall.NoopFirewallDriver')
  set_config_ini(novaConf, 'DEFAULT', 'security_group_api', 'neutron')
  set_config_ini(novaConf, 'DEFAULT', 'service_neutron_metadata_proxy', 'True')
  set_config_ini(novaConf, 'DEFAULT', 'neutron_metadata_proxy_shared_secret', 'helloOpenStack')
  set_config_ini(novaConf, 'DEFAULT', 'volume_api_class', 'nova.volume.cinder.API')
  set_config_ini(novaConf, 'DEFAULT', 'osapi_volume_listen_port', '5900')
  set_config_ini(novaConf, 'DEFAULT', 'compute_driver', 'libvirt.LibvirtDriver')
  novaPasteApiConf = '/etc/nova/api-paste.ini'
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'auth_host', controlNodeIP)
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'auth_port', '35357')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'auth_protocol', 'http')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'admin_tenant_name', 'service')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'admin_user', 'nova')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'admin_password', 'nova')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'signing_dir', '/tmp/keystone-signing-nova')
  set_config_ini(novaPasteApiConf, 'filter:authtoken', 'auth_version', 'v2.0')
  run_command("nova-manage db sync")
  run_command("service nova-api restart", True)
  run_command("service nova-cert restart", True)
  run_command("service nova-scheduler restart", True)
  run_command("service nova-conductor restart", True)
  run_command("service nova-consoleauth restart", True)
  run_command("service nova-novncproxy restart", True)
  time.sleep(10)
  run_command("nova-manage service list", True)
  log('Completed Nova')
#######################################################################


#######################################################################
def install_ntp(ipControlNode):
  if not ipControlNode or len(str(ipControlNode)) == 0:
    raise Exception("Unable to install/configure NTP, no control node IP specified")
  print ''
  log('Installing NTP')
  run_command("apt-get install -y ntp" , True)
  log('Configuring NTP')
  run_command("sed -i 's/^server 0.ubuntu.pool.ntp.org/#server 0.ubuntu.pool.ntp.org/g' /etc/ntp.conf")
  run_command("sed -i 's/^server 1.ubuntu.pool.ntp.org/#server 1.ubuntu.pool.ntp.org/g' /etc/ntp.conf")
  run_command("sed -i 's/^server 2.ubuntu.pool.ntp.org/#server 2.ubuntu.pool.ntp.org/g' /etc/ntp.conf")
  run_command("sed -i 's/^server 3.ubuntu.pool.ntp.org/#server 3.ubuntu.pool.ntp.org/g' /etc/ntp.conf")
  run_command("sed -i 's/^server .*/server %s/g' /etc/ntp.conf" %ipControlNode)
  run_command("service ntp restart", True)
  log('Completed NTP')
#######################################################################


#######################################################################
def install_rabbitmq():
  print ''
  log('Installing RabbitMQ')
  run_command("apt-get install -y rabbitmq-server" , True)
  run_command("service rabbitmq-server restart", True)
  time.sleep(10)
  log('Completed RabbitMQ')
#######################################################################


#######################################################################
def log(message):
  if message and len(str(message)) > 0:
    print datetime.now().strftime('%m/%d/%Y %H:%M:%S,%f') + " " + str(message)
#######################################################################


#######################################################################
def run_command(command, display=False):
  if not command or command is None:
    raise Exception("Unable to run command, no command specified")
  #log("Running: " + str(command))
  process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  if display:
    while True:
      nextline = process.stdout.readline()
      if nextline == '' and process.poll() != None:
        break
      sys.stdout.write(nextline)
      sys.stdout.flush()

  output, stderr = process.communicate()
  exitCode = process.returncode

  if (exitCode == 0):
    return output.strip()
  else:
    log("Failed to run: " + str(command))
    raise Exception(str(output) + ', return code: ' + str(exitCode))
#######################################################################


#######################################################################
def run_db_command(rootPassword, command):
  if not rootPassword or len(str(rootPassword)) == 0:
    raise Exception("Unable to run database command, no root password specified")
  if not command or len(str(command)) == 0:
    raise Exception("Unable to run database command, no command specified")
  cmd = """mysql -uroot -p%s -e "%s" """ % (rootPassword, command)
  output = run_command(cmd)
  return output
#######################################################################


#######################################################################
def set_config_ini(filePath, section, key, value):
  if not os.path.exists(filePath):
    raise Exception("Unable to set config value in INI, file " + str(filePath) + " does not exist")
  if not os.path.isfile(filePath):
    raise Exception("Unable to set config value in INI, path " + str(filePath) + " is not a file")
  global iniparse
  if iniparse is None:
    iniparse = __import__('iniparse')
  config = iniparse.ConfigParser()
  config.readfp(open(filePath))
  if not config.has_section(section):
    config.add_section(section)
    value += '\n'
  config.set(section, key, value)
  with open(filePath, 'w') as f:
    config.write(f)
#######################################################################
