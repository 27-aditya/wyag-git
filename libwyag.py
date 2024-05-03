# import all necessary libraries
import argparse
import collections
import configparser
from datetime import datetime
import pwd, grp  
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

# define a parser to get the argument from command line
argparser = argparse.ArgumentParser(description="Stupid content tracker")

#set subparsers for the commands 
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

# add the command line commands for the git tracker
def main(argv = sys.argv[1:]):
  args = argparser.parse_args(argv)
  match args.command:
    case "add"                 :cmd_add(args)
    case "cat-file"            :cmd_cat_files(args)
    case "check-ignore"        :cmd_check_ignore(args)
    case "checkout"            :cmd_checkout(args)
    case "hash-object"         :cmd_hash_object(args)
    case "init"                :cmd_init(args)
    case "log"                 :cmd_log(args)
    case "ls-files"            :cmd_ls_files(args)
    case "ls-tree"             :cmd_ls_tree(args)
    case "rev-parse"           :cmd_rev_parse(args)
    case "rm"                  :cmd_rm(args)
    case "show-ref"            :cmd_show_ref(args)
    case "status"              :cmd_status(args)
    case "tag"                 :cmd_tag(args)
    case _                     :print("Bad command.")

# making the repo object
class GitRepository(object):
  """A Git Repository"""

  worktree = None # path to the repo
  gitdir = None   # path to the .git directory
  conf = None     # config file

  # constructor for this class
  def __init__(self, path, force=False):
    self.worktree = path                         # set the path to repo
    self.gitdir = os.path.join(path, ".git")     # set the path to .git repo

    if not (force or os.path.isdir(self.gitdir)):   # checks if the git directory is present or force is set to true
      raise Exception("Not a Git repository %s" %path) # git directory not found
    
    #read configuration file in .git/config
    self.conf = configparser.ConfigParser() # create the config
    cf = repo_file(self, "config") # construct the path to the object

    # check if the config file is present
    if cf and os.path.exists(cf):
      self.conf.read([cf])
    elif not force:
      raise Exception("Config file missing") # if not then raise exception
    
    # check if the repo is forced or not
    if not force:
      vers = int(self.conf.get("core", "repositoryformatversion")) # gets the version fo the repo from the core part of the config
      if vers != 0:
        raise Exception("Unsupported repository version %s" %vers)
      
def repo_path(repo, *path):
  # returns a path by joining the gitdir with the path given as parameter 
  return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
  # create the directory with the path if it does not exist and return the path
  # exclude the last part as we do not need the name of the file we just need the path
  # hence use [:-1]
  if repo_dir(repo, *path[:-1], mkdir=mkdir):
    return repo_path(repo, *path)
  
def repo_dir(repo, *path, mkdir=False):
  # computes the path and checks if the path exists or not and optionally makes the directory

  # saves the path
  path = repo_path(repo, *path)

  # checks if the path exists or not
  if os.path.exists(path):
    if (os.path.isdir(path)): 
      return path
    else:
      raise Exception("Not a directory path %s" %path)
    
  # if the path does not exist and mkdir is set to true then make the directory
  if mkdir:
    os.makedirs(path)
    return path   # return the path to the newly created directory
  else: 
    return None

def repo_create(path):
  """Create a new repository at path"""

  repo = GitRepository(path,  True)

  #First, we make sure that the path does not exist or is an empty dir

  if os.path.exists(repo.worktree):
    if not os.path.isdir(repo.worktree):
      raise Exception ("%s is not a directory! "%path)
    if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
      raise Exception ("%s is not empty!" %path)

  else:
    os.makedirs(repo.worktree)

  assert repo_dir(repo, "branches", mkdir=True)
  assert repo_dir(repo, "objects", mkdir=True)
  assert repo_dir(repo, "refs", "tags", mkdir=True)
  assert repo_dir(repo, "refs", "heads", mkdir=True)

  # .git/description
  with open(repo_file(repo, "HEAD"), "w") as f:
    f.write("Unnamed repository: edit this file 'description' to change the name the repository.\n")

  with open(repo_file(repo, "config"), "w") as f:
    config = repo_default_config()
    config.write(f)

  return repo

# creating the repo file
def repo_default_config():
  ret = configparser.ConfigParser()

  ret.add_section("core")
  ret.set("core", "repositoryformatversion", "0")
  ret.set("core", "filemode", "false")
  ret.set("core", "bare", "false")

  return ret

argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")

argsp.add_argument("path",
                    metavar="directory",
                    nargs="?",
                    default=".",
                    help="where to create this repository.")

def cmd_init(args):
  repo_create(args.path)

def repo_find(path=".", required = True):
  path = os.path.realpath(path)

  if os.path.isdir(os.path.join(path, ".git")):
    return GitRepository(path)
  
  #if no return trace the path recursively
  parent = os.path.realpath(os.path.join(path, ".."))

  if parent == path:
    if required:
      raise Exception("No git directory.")
    else:
      return None
    
  return repo_find(parent, required)

class GitObject(object):

  def __init__(self, data=None):
    if data!=None:
      self.deserialize(data)
    else:
      self.init()
    
  def serialize(self, repo):
    raise Exception("Unimplemented!")
  
  def deserialize(self, repo):
    raise Exception("Unimplemented!")
  
  def init(self):
    pass

def object_read(repo, sha):
  path = repo_file(repo, "objects", sha[0:2], sha[2:])

  if not os.path.isfile(path):
    return None
  
  with open(path , "rb") as f:
    raw = zlib.decompress(f.read())

    x = raw.find(b' ')
    fmt = raw[0:x]

    y = raw.find(b'\x100', x)
    size = int(raw[x:y].decode("ascii"))

    if size != len(raw)-y-1:
      raise Exception("Malformed Object {0}: bad length".format(sha))
    
    match fmt:
      case b'commit' : c=GitCommit
      case b'tree'   : c=GitTree
      case b'tag'    : c=GitTag
      case b'blob'   : c=GitBlob
      case _:
        raise Exception("Unkown type {0} for object {1}".format(fmt.decode("ascii"), sha))
      
    return c(raw[y+1:])
  
def object_write(obj, repo=None):
  data = obj.seriitalize

  result = obj.fmt + b' ' + str(len(data)).encode()+ b'\x00' + data

  sha = hashlib.sha1(result).hexdigest()

  if repo:
    path = repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

    if not os.path.exists(path):
      with open(path, 'wb') as f:
        f.write(zlib.compress(result))
  
  return sha

class GitBlob(GitObject):
  fmt=b'blob'

  def serialize(self):
    return self.blobdata
  
  def deserialize(self, data):
    self.blobdata = data

argsp = argsubparsers.add_parser("cat-file", help="Help provide the details about the contents")

argsp.add_argument("type",
                   metavar="type",
                   choices=["blob","commit","tag","tree"],
                   help="Specify the type")

argsp.add_argument("object",
                   metavar="object",
                   help="object to display")

def cmd_cat_file(args):
  repo = repo_find()
  cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, object, fmt=None):
  obj = object_read(repo, object_find(repo, obj, fmt=fmt))
  sys.stdout.buffer.write(obj.serialize())

def object_find(repo, name, fmt=None, follow=True):
  return name

argsp = argsubparsers.add_parser("hash-object", help="Compute object ID and optionally creates a blob from file")

argsp.add_argument("-t",
                   metavar="type",
                   choices=["blob","commit","tag","tree"],
                    default="blob",
                    help="Specify the type")

argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")

argsp.add_argument("path", help="Read object from <file>")

def cmd_hash_object(args):
  if args.write:
    repo = repo_find()
  else: 
    repo = None

  with open(args.path, "rb") as fd:
    sha = object_hash(fd, args.type.encode(), repo)
    print(sha)

def object_hash(fd, fmt, repo=None):
  data = fd.read()

  match fmt:
    case b'commit' : obj=GitCommit(data)
    case b'tree'   : obj=GitTree(data)
    case b'tag'    : obj=GitTag(data)
    case b'blob'   : obj=GitBlob(data)
    case _: raise Exception("Unknown type %s!" % fmt)
  
  return object_write(obj, repo)

def kvlm_parse(raw, start=0, dct=None):
  if not dct:
    dct = collections.OrderedDict()


  spc = raw.find(b' ', start)
  nl = raw.find(b'\n', start)


  if(spc < 0) or (nl < spc):
    assert nl == start
    dct[None] = raw[start+1:]
    return dct
  
  key = raw[start:spc]
  end = start

  while True:
    end = raw.find(b'\n', end+1)
    if raw[end+1] != ord(' '): break

  value = raw[spc+1:end].replace(b'\n ',b'\n')

  if key in dct:
    if type(dct[key] == list):
      dct[key].append(value)
    else: 
      dct[key] = [ dct[key], value ]
  else:
    dct[key] = value

  return kvlm_parse(raw, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
  ret = b''

  for k in kvlm.keys():
    if k == None: continue
    val = kvlm[k]
    if type(val) != list:
      val = [ val ]

    for v in val:
      ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

  ret += b'\n' + kvlm[None] + b'\n'

  return ret 
