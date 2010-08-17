#!/usr/bin/env python

import logging
import optparse
import os
import socket
import sys
import traceback
import ConfigParser
from StringIO import StringIO
import readline
import string
import time
from random import Random
from nimbusweb.setup import pathutil,javautil,checkssl,gtcontainer,autoca,derbyutil
from nimbusweb.setup.setuperrors import *

CONFIGSECTION = 'nimbussetup'
DEFAULTCONFIG = """
[nimbussetup]

# relative to base directory
hostcert: var/hostcert.pem
hostkey: var/hostkey.pem
ca.dir: var/ca
ca.trustedcerts.dir: var/ca/trusted-certs

gridmap: services/etc/nimbus/nimbus-grid-mapfile

keystore: var/keystore.jks
keystore.pass: changeit

services.enabled: True
services.wait: 10
web.enabled: False
cumulus.enabled: True
"""
CONFIG_STATE_PATH = 'nimbus-setup.conf'

CA_NAME_QUESTION = """
Nimbus uses an internal Certificate Authority (CA) for some services. This CA
is also used to generate host and user certificates if you do not have your own.

This CA will be created in %(ca.dir)s

Please pick a unique, one word CA name or hit ENTER to use a UUID.

For example, if you are installing this on the "Jupiter" cluster, you might use
"JupiterNimbusCA" as the name.
"""

CONFIG_HEADER = """
# Autogenerated at %(time)s
#
# This file contains configuration values used by the nimbus-configure program.
# If you want to change any of these values, you may edit this file, but you
# must run nimbus-configure before the change will take effect.

"""

ENVFILE_BODY = """
# Autogenerated at %(time)s
#
# This file contains environment variables which are necessary to use some of
# the Nimbus internal tools directly

NIMBUS_HOME=%(NIMBUS_HOME)s
export NIMBUS_HOME

GLOBUS_LOCATION=%(GLOBUS_LOCATION)s
export GLOBUS_LOCATION

X509_CERT_DIR=%(X509_CERT_DIR)s
export X509_CERT_DIR
"""

KEYSTORE_MISMATCH_MSG = """
A Java keystore already exists at:
    %(keystore)s
However, it does not contain the host certificate and private key which are
being configured.
    Certificate: %(hostcert)s
    Private key: %(hostkey)s
This may be because you have switched certificates and the keystore contains
the old version. If so, the best solution is to delete (or relocate) the 
keystore and rerun nimbus-configure to generate a new one.
"""

def getlog(override=None):
    """Allow developer to replace logging mechanism, e.g. if this
    module is incorporated into another program as an API.

    Keyword arguments:

    * override -- Custom logger (default None, uses global variable)

    """
    global _log
    if override:
        _log = override
    try:
        _log
    except:
        _log = logging.getLogger("nimbussetup")
        _log.setLevel(logging.DEBUG)
    return _log
    
def configureLogging(level, formatstring=None, logger=None):
    """Configure the logging format and mechanism.  Sets global 'log' variable.
    
    Required parameter:
        
    * level -- log level

    Keyword arguments:

    * formatstring -- Custom logging format (default None, uses time+level+msg)

    * logger -- Custom logger (default None)
    """
    
    global log
    
    logger = getlog(override=logger)
    
    if not formatstring:
        formatstring = "%(asctime)s (%(filename)s:%(lineno)d): %(message)s"
    
    formatter = logging.Formatter(formatstring)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # set global variable
    log = logger
    
    log.debug("debug enabled")

def getconfig(filepath=None):
    config = ConfigParser.SafeConfigParser()
    
    fh = StringIO(DEFAULTCONFIG)
    config.readfp(fh)
    if filepath:
        for path in config.read(filepath):
            log.debug("Read config from: '%s'" % path)
    return config
    
class ARGS:
    """Class for command-line argument constants"""

    BASEDIR_LONG = "--basedir"
    BASEDIR = "-b"
    BASEDIR_HELP = "Path to base Nimbus directory"

    CONFIGPATH_LONG = "--conf"
    CONFIGPATH = "-c"
    CONFIGPATH_HELP = "Path to configuration file"
    
    DEBUG_LONG = "--debug"
    DEBUG = "-d"
    DEBUG_HELP = "Log debug messages"

    HOSTNAME_LONG = "--hostname"
    HOSTNAME = "-H"
    HOSTNAME_HELP = "Fully qualified hostname of machine"

    CANAME_LONG= "--caname"
    CANAME = "-n"
    CANAME_HELP = "Unique name to give CA"
    
    HOSTKEY_LONG = "--hostkey"
    HOSTKEY = "-k"
    HOSTKEY_HELP = "Path to PEM-encoded host private key"

    HOSTCERT_LONG = "--hostcert"
    HOSTCERT = "-C"
    HOSTCERT_HELP = "Path to PEM-encoded host certificate"

    AUTOCONFIG_LONG= "--autoconfig"
    AUTOCONFIG_HELP = "Run the Nimbus autoconfig tool to test VMM communication"
    
    IMPORTDB_LONG= "--import-db"
    IMPORTDB_HELP = "Import a Nimbus accounting database from another install"
    
    PRINT_HOSTNAME_LONG = "--print-hostname"
    PRINT_HOSTNAME = "-Z"
    PRINT_HOSTNAME_HELP = "Print chosen hostname or error if none chosen"
    
    PRINT_REPOBUCKET_LONG = "--print-repobucket"
    PRINT_REPOBUCKET = "-R"
    PRINT_REPOBUCKET_HELP = "Print repo bucket for Cumulus"
    
def validateargs(opts):
    
    seeh = "see help (-h)"

    if not opts.basedir:
        raise InvalidInput("%s required, %s." % (ARGS.BASEDIR_LONG, seeh))

    if opts.configpath and not os.path.exists(opts.configpath):
        raise InvalidInput("%s file specified does not exist: '%s'" % 
                (ARGS.CONFIGPATH_LONG, opts.configpath))

    if opts.hostkey or opts.hostcert:
        if not (opts.hostkey and opts.hostcert):
            raise InvalidInput(
                    "You must specify both %s and %s paths, or neither" % 
                    (ARGS.HOSTCERT_LONG, ARGS.HOSTKEY_LONG))
        if not os.path.exists(opts.hostkey):
            raise InvalidInput("The specified host key does not exist: %s" %
                    opts.hostkey)
        if not os.path.exists(opts.hostcert):
            raise InvalidInput("The specified host cert does not exist: %s" %
                    opts.hostcert)

def parsersetup():
    """Return configured command-line parser."""

    ver = "Nimbus setup"
    usage = "see help (-h)."
    parser = optparse.OptionParser(version=ver, usage=usage)

    group = optparse.OptionGroup(parser, "Actions", "-------------")
    group.add_option(ARGS.AUTOCONFIG_LONG,
                    action="store_true", dest="autoconfig",
                    default=False, help=ARGS.AUTOCONFIG_HELP)
    
    group.add_option(ARGS.IMPORTDB_LONG,
            dest="importdb", metavar="PATH", help=ARGS.IMPORTDB_HELP)

    group.add_option(ARGS.PRINT_HOSTNAME, ARGS.PRINT_HOSTNAME_LONG,
                    action="store_true", dest="print_chosen_hostname",
                    default=False, help=ARGS.PRINT_HOSTNAME_HELP)
    
    group.add_option(ARGS.PRINT_REPOBUCKET, ARGS.PRINT_REPOBUCKET_LONG,
                    action="store_true", dest="print_repo_bucket",
                    default=False, help=ARGS.PRINT_REPOBUCKET_HELP)
    
    parser.add_option_group(group)
    
    group = optparse.OptionGroup(parser,  "Misc options", "-------------")

    group.add_option(ARGS.DEBUG, ARGS.DEBUG_LONG,
                      action="store_true", dest="debug", default=False, 
                      help=ARGS.DEBUG_HELP)
    
    group.add_option(ARGS.CONFIGPATH, ARGS.CONFIGPATH_LONG,
                    dest="configpath", metavar="PATH",
                    help=ARGS.CONFIGPATH_HELP)
    
    group.add_option(ARGS.BASEDIR, ARGS.BASEDIR_LONG,
                    dest="basedir", metavar="PATH",
                    help=ARGS.BASEDIR_HELP)
    
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "Configuration options", 
            "-------------")
    
    group.add_option(ARGS.HOSTNAME, ARGS.HOSTNAME_LONG,
            dest="hostname", metavar="HOST", help=ARGS.HOSTNAME_HELP)

    group.add_option(ARGS.CANAME, ARGS.CANAME_LONG,
            dest="ca_name", metavar="NAME", help=ARGS.CANAME_HELP)

    group.add_option(ARGS.HOSTKEY, ARGS.HOSTKEY_LONG,
            dest="hostkey", metavar="PATH", help=ARGS.HOSTKEY_HELP)

    group.add_option(ARGS.HOSTCERT, ARGS.HOSTCERT_LONG,
            dest="hostcert", metavar="PATH", help=ARGS.HOSTCERT_HELP)
    parser.add_option_group(group)
    return parser

def fold_opts_to_config(opts, config):
    if opts.hostname:
        config.set(CONFIGSECTION, 'hostname', opts.hostname)
    if opts.ca_name:
        config.set(CONFIGSECTION, 'ca.name', opts.ca_name)
    if opts.hostkey:
        config.set(CONFIGSECTION, 'hostkey', opts.hostkey)
    if opts.hostcert:
        config.set(CONFIGSECTION, 'hostcert', opts.hostcert)

def get_user_input(valuename, default=None, required=True):
    answer = None
    question = valuename + (default and ("(%s): " % default) or ": ")
    while not answer:
        value = raw_input(valuename+": ")
        if value:
            answer = value.strip()
        elif default:
            answer = default
        if not answer:
            if required:
                print "Invalid input. You must specify a value. Or hit Ctrl-C to give up."
            else:
                return None

    return answer

class NimbusSetup(object):
    def __init__(self, basedir, config, interactive=True):
        self.basedir = basedir
        self.config = config
        self.interactive = interactive

        self.webdir = self.resolve_path('web/')
        self.gtdir = self.resolve_path('services/')
        self.cadir = self.resolve_config_path('ca.dir')
        self.trustedcertsdir = self.resolve_config_path('ca.trustedcerts.dir')
        self.hostcert_path = self.resolve_config_path('hostcert')
        self.hostkey_path = self.resolve_config_path('hostkey')
        self.keystore_path = self.resolve_config_path('keystore')
        self.gridmap_path = self.resolve_config_path('gridmap')
        self.envfile_path = self.resolve_path('libexec/environment.sh')
    
    def __getitem__(self, key):
        try:
            return self.config.get(CONFIGSECTION, key)
        except ConfigParser.NoOptionError:
            return None

    def __setitem__(self, key, value):
        return self.config.set(CONFIGSECTION, key, value)

    def validate_environment(self):
        if not pathutil.is_absolute_path(self.basedir):
            raise IncompatibleEnvironment(
                    "Base directory setting is not absolute")
        pathutil.ensure_dir_exists(self.basedir, "base")
        pathutil.ensure_dir_exists(self.webdir, "web")
        pathutil.ensure_dir_exists(self.gtdir, "GT container")
        
        # check that we have some java
        javautil.check(self.webdir, log)

    def resolve_path(self, path):
        """
        Resolves a path relative to base directory. If absolute, returns as-is.
        If relative, joins with self.basedir and returns.
        """
        if os.path.isabs(path):
            return path
        return os.path.join(self.basedir, path)

    def resolve_config_path(self, config):
        """
        Resolves a path, like resolve_path(), but from a config key.
        """
        path = self[config]
        if path:
            return self.resolve_path(path)
        return None
    
    def ask_hostname(self):
        hostguess = self['hostname']
        if not hostguess:
            hostguess = socket.getfqdn()

        if self.interactive:
            print "\nWhat is the fully qualified hostname of this machine?\n"
            print "Press ENTER to use the detected value (%s)\n" % hostguess
            hostname = get_user_input("Hostname", default=hostguess)
        else:
            print "Using hostname: '%s'" % hostguess
            hostname = hostguess
        return hostname

    def ask_ca_name(self):
        ca_name_config = self['ca.name']

        if self.interactive:
            print CA_NAME_QUESTION % {'ca.dir' : self.cadir}
            ca_name = get_user_input("CA Name", default=ca_name_config,
                    required=False)
            if not ca_name:
                ca_name = pathutil.uuidgen()
                print "You did not enter a name, using '%s'" % ca_name
        else:
            ca_name = ca_name_config or pathutil.uuidgen()
            print "Creating CA with name: '%s'" % ca_name
        return ca_name

    def write_env_file(self):
        """Writes an environment file users can source."""
        f = None
        try:
            f = open(self.envfile_path,'w')
            text = ENVFILE_BODY % {
                    'time' : time.strftime('%c'),
                    'NIMBUS_HOME' : self.basedir,
                    'GLOBUS_LOCATION' : self.gtdir,
                    'X509_CERT_DIR' : self.trustedcertsdir
                    }
            f.write(text)
        finally:
            if f:
                f.close()

    def write_db_props(self):
        """Writes ant properties file used by db-mgmt.xml
        """
        persistdir = os.path.join(self.gtdir, 'var/nimbus')
        dbsetupdir = os.path.join(self.gtdir, 'share/nimbus')
        dbsetuplibdir = os.path.join(self.gtdir, 'share/nimbus/lib')
        derbyhomedir = os.path.join(self.gtdir, 'var')
        derbylibdir = os.path.join(self.gtdir, 'lib')
        pwgenfile = os.path.join(self.gtdir, 'etc/nimbus/workspace-service/other/shared-secret-suggestion.py')

        lines = ['#Autogenerated by nimbus-configure\n', 
                '#'+time.strftime('%c')+'\n']
        lines.append('workspace.dbdir.prop=%s\n' % persistdir)
        lines.append('workspace.sqldir.prop=%s\n' % dbsetuplibdir)
        lines.append('workspace.notifdir.prop=%s\n' % dbsetuplibdir)
        lines.append('derby.system.home.prop=%s\n' % derbyhomedir)
        lines.append('derby.relative.dir.prop=nimbus\n')
        lines.append('derby.classpath.dir.prop=%s\n' % derbylibdir)
        lines.append('pwGen.path.prop=%s\n' % pwgenfile)

        db_props_path = os.path.join(dbsetupdir,'workspace.persistence.conf')
        f = None
        try:
            f = open(db_props_path, 'w')
            f.writelines(lines)
        finally:
            if f:
                f.close()

    def write_cumulus_props(self):
        """Writes cumulus.conf file
        """
        
        if not self['hostname']:
            err = "hostname should have been determined already"
            raise UnexpectedError(err)
            
        cumulus_authz_db = os.path.join(self.basedir, 'cumulus/etc/authz.db')
        repo_bucket = self.get_repobucket_no_asking()
            
        lines = ['#Autogenerated by nimbus-configure\n', 
                '#'+time.strftime('%c')+'\n']
        
        lines.append("\n")
        lines.append("# Generally these settings are auto-generated by nimbus-configure.\n")
        lines.append("\n")
        
        lines.append("cumulus.authz.db=%s\n" % cumulus_authz_db)
        lines.append("cumulus.repo.dir=%s/cumulus/posixdata\n" % (self.basedir))
        lines.append("cumulus.host=%s\n" % self['hostname'])
        lines.append("cumulus.repo.bucket=%s\n" % repo_bucket)
        lines.append("cumulus.repo.prefix=VMS\n")
        
        cumulus_conf_path = os.path.join(self.gtdir, 'etc/nimbus/workspace-service/cumulus.conf')
        f = None
        try:
            f = open(cumulus_conf_path, 'w')
            f.writelines(lines)
        finally:
            if f:
                f.close()

    def write_cumulus_init(self):
        cumulus_ini_file = os.path.join(self.basedir, 'cumulus/etc/cumulus.ini')

        s = ConfigParser.SafeConfigParser()
        try:
            s.readfp(open(cumulus_ini_file, "r"))
        except:
            raise Exception("Could not open %s for parsing" % (cumulus_ini_file))

        s.set("https", "enabled", "False")
        s.set("https", "key", self.hostkey_path)
        s.set("https", "cert", self.hostcert_path)
        s.set("cb", "hostname", self['hostname'])
        s.write(open(cumulus_ini_file, "w"))

    def get_hostname_or_ask(self):
        if self['hostname']:
            hostname = self['hostname']
            log.debug('Using configured hostname: "%s". Run with %s to change.',
                    hostname, ARGS.HOSTNAME_LONG)
        else:
            hostname = self.ask_hostname()
            self['hostname'] = hostname
        return hostname
        
    def get_hostname_no_asking(self):
        # could be None
        return self['hostname']
            
    def get_repobucket_no_asking(self):
        # at least get this to one exact place, can determine dynamically later
        return "Repo"

    def perform_setup(self):
        # first, set up CA and host cert/key
        ca_name = self["ca.name"]
        if not os.path.exists(self.cadir):
            ca_name = self.ask_ca_name()
            self['ca.name'] = ca_name
            autoca.createCA(ca_name, self.webdir, self.cadir, log)
        if not ca_name:
            raise InvalidConfig("CA name is unknown")

        ca_cert = os.path.join(self.cadir, 'ca-certs/%s.pem' % ca_name)
        ca_key = os.path.join(self.cadir, 'ca-certs/private-key-%s.pem' % ca_name)
        pathutil.ensure_file_exists(ca_cert, "CA certificate")
        pathutil.ensure_file_exists(ca_key, "CA private key")

        hostname = self.get_hostname_or_ask()

        #TODO the hostcert/key creation should be extracted from here
        # right now it just does a bunch of redundant checks first
        checkssl.run(self.webdir, self.hostcert_path, self.hostkey_path, log, 
                cadir=self.cadir, hostname=hostname)

        password = self['keystore.pass']
        if not password:
            raise InvalidConfig("Keystore password is unknown")

        try:
            autoca.ensureKeystore(self.hostcert_path, self.hostkey_path, 
                    self.keystore_path, password, self.webdir, log)
        except autoca.KeystoreMismatchError:
            raise IncompatibleEnvironment(KEYSTORE_MISMATCH_MSG % {
                'keystore' : self.keystore_path,
                'hostcert' : self.hostcert_path,
                'hostkey' : self.hostkey_path })
        pathutil.make_path_rw_private(self.keystore_path)

        # then adjust the web config to point to these keys
        
        webconfpath = pathutil.pathjoin(self.webdir, 'nimbusweb.conf')
        webconf = ConfigParser.SafeConfigParser()
        if not webconf.read(webconfpath):
            raise IncompatibleEnvironment(
                    "nimbus web config does not exist: %s" % webconfpath)
        relpath = pathutil.relpath
        webconf.set('nimbusweb', 'ssl.cert', 
                relpath(self.hostcert_path, self.webdir))
        webconf.set('nimbusweb', 'ssl.key', 
                relpath(self.hostkey_path, self.webdir))
        webconf.set('nimbusweb', 'ca.dir', relpath(self.cadir, self.webdir))

        webconffile = open(webconfpath, 'wb')
        try:
            webconf.write(webconffile)
        finally:
            webconffile.close()

        # then setup GT container
        gtcontainer.adjust_hostname(hostname, self.webdir, self.gtdir, log)
        gtcontainer.adjust_secdesc_path(self.webdir, self.gtdir, log)
        gtcontainer.adjust_host_cert(self.hostcert_path, self.hostkey_path, 
                self.webdir, self.gtdir, log)
        gtcontainer.adjust_gridmap_file(self.gridmap_path, self.webdir, 
                self.gtdir, log)

        # and context broker
        gtcontainer.adjust_broker_config(ca_cert, ca_key, self.keystore_path,
                password, self.webdir, self.gtdir, log)

        # run the web newconf script, if enabled
        if self.config.getboolean(CONFIGSECTION, 'web.enabled'):
            ret = os.system(os.path.join(self.webdir, 'sbin/new-conf.sh'))
            configured = pathutil.pathjoin(self.webdir, ".nimbusconfigured")
            if not os.path.isfile(configured):
                open(configured, "a")
                

        # write an enviroment file
        self.write_env_file()

        # and db properties file
        self.write_db_props()
        
        # and cumulus properties file
        self.write_cumulus_props()
        self.write_cumulus_init()

def import_db(setup, old_db_path):
    derbyrun_path = os.path.join(setup.gtdir, 'lib/derbyrun.jar')
    if not os.path.exists(derbyrun_path):
        raise IncompatibleEnvironment("derbyrun.jar does not exist: %s" %
                derbyrun_path)
    ij_path = "java -jar %s ij" % derbyrun_path

    new_db_path = os.path.join(setup.gtdir, 'var/nimbus/WorkspaceAccountingDB')
    if not os.path.isdir(new_db_path):
        raise IncompatibleEnvironment("Could not find current Accounting DB: %s"
                % new_db_path)

    if not os.path.isdir(old_db_path):
        raise InvalidInput("Specified DB does not exist or is not a directory")

    if derbyutil.update_db(ij_path, old_db_path, new_db_path) == 1:
        raise UnexpectedError("Failed to update Accounting DB")

def generate_password(length=25):
    okchars = string.letters + string.digits + "!@^_&*+-"
    return ''.join(Random().sample(okchars, length))

def main(argv=None):
    if os.name != 'posix':
        print >>sys.stderr, "\nERROR: Only runs on POSIX systems."
        return 3

    if sys.version_info < (2,4):
        print >>sys.stderr, "\nERROR: Your system must have Python version 2.4 or later. "
        print >>sys.stderr, 'Detected version: "'+sys.version+'"'
        return 4
        
    parser = parsersetup()

    if argv:
        (opts, args) = parser.parse_args(argv[1:])
    else:
        (opts, args) = parser.parse_args()
        
    global log
    log = None
    
    try:
        configureLogging(opts.debug and logging.DEBUG or logging.INFO)
        
        validateargs(opts)
        
        basedir = opts.basedir
        log.debug("base directory: %s" % basedir)
        config_state_path = os.path.join(basedir, CONFIG_STATE_PATH)
        paths = [config_state_path]
        if opts.configpath:
            paths.append(opts.configpath)
        config = getconfig(filepath=paths)
        #Some command line options are folded into the config object
        fold_opts_to_config(opts, config)
            
        setup = NimbusSetup(basedir, config)
        setup.validate_environment()
        
        if opts.autoconfig:
            cmd = os.path.join(setup.gtdir, 
                    'share/nimbus-autoconfig/autoconfig.sh')
            if not (os.path.exists(cmd) and os.access(cmd, os.X_OK)):
                print >>sys.stderr, "\nERROR: autoconfig script not found or not executable: " + cmd
                return 1
            os.system(cmd)
            return 0

        elif opts.importdb:
            import_db(setup, opts.importdb)
            return 0
        elif opts.print_repo_bucket:
            bucket = setup.get_repobucket_no_asking()
            if not bucket:
                return 1
            else:
                print bucket
                return 0
        elif opts.print_chosen_hostname:
            hostname = setup.get_hostname_no_asking()
            if not hostname:
                return 1
            else:
                print hostname
                return 0
        else:
            setup.perform_setup()

        log.debug("saving settings to %s" % config_state_path)
        try:
            f = None
            try:
                f = open(config_state_path, 'wb')
                f.write(CONFIG_HEADER % {'time' : time.strftime('%c')})
                config.write(f)
            except:
                log.info("Failed to save settings to %s!" % config_state_path)
        finally:
            if f:
                f.close()
                    
        # using instead of 0 for now, as a special signal to the wrapper program
        return 42

    except InvalidInput, e:
        msg = "\nProblem with input: %s" % e.msg
        print >>sys.stderr, msg
        return 1

    except InvalidConfig, e:
        msg = "\nProblem with configuration: %s" % e.msg
        print >>sys.stderr, msg
        return 2

    except IncompatibleEnvironment, e:
        msg = "\nCannot validate environment: %s" % e.msg
        print >>sys.stderr, msg
        if opts.debug:
            print >>sys.stderr, "\n---------- stacktrace ----------"
            traceback.print_tb(sys.exc_info()[2])
            print >>sys.stderr, "--------------------------------"
        return 3

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print "\n\nReceived keyboard interrupt. Aborting!\n"
        sys.exit(5)
    except:
        exception_type = sys.exc_type
        try:
            exceptname = exception_type.__name__ 
        except AttributeError:
            exceptname = exception_type
        name = str(exceptname)
        err = str(sys.exc_value)
        errmsg = "\n==> Uncaught problem, please report all following output:\n  %s: %s" % (name, err)
        print >>sys.stderr, errmsg
        traceback.print_tb(sys.exc_info()[2])
        sys.exit(97)
