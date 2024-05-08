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

# creating the repo
def repo_create(path):

  repo = GitRepository(path,  True)

  # first, we make sure that the path does not exist or is an empty dir

  # if the path exists and is not a directory then raise an exception
  if os.path.exists(repo.worktree):
    if not os.path.isdir(repo.worktree):
      raise Exception ("%s is not a directory! "%path)
    # if the gitdir exists and is not empty then raise an exception
    if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
      raise Exception ("%s is not empty!" %path)

  # if the path does not exist then create the directory
  else:
    os.makedirs(repo.worktree)

  # calls the repodir function and creates the required directories for branches, objects, refs, tags, heads
  assert repo_dir(repo, "branches", mkdir=True)
  assert repo_dir(repo, "objects", mkdir=True)
  assert repo_dir(repo, "refs", "tags", mkdir=True)
  assert repo_dir(repo, "refs", "heads", mkdir=True)

  # .git/description
  # opens the head file as f and writes the description to it
  with open(repo_file(repo, "HEAD"), "w") as f:
    f.write("Unnamed repository: edit this file 'description' to change the name the repository.\n")

  # opens the config file and writes the default configuration to it
  with open(repo_file(repo, "config"), "w") as f:
    config = repo_default_config()
    config.write(f)

  return repo

# creating the repo configuration
def repo_default_config():
  # set the default configuration for the repository
  ret = configparser.ConfigParser()

  # add a core section to the config
  ret.add_section("core")
  # add repo version set to 0
  ret.set("core", "repositoryformatversion", "0")
  # add repo filemode set to false to show no changes have taken place yet
  ret.set("core", "filemode", "false")
  # add repo bare to show that the repo is not bare
  ret.set("core", "bare", "false")

  return ret

# define the init command for the git tracker
argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")

# add arguments to the init command: path, directory, no args, default case, help message
argsp.add_argument("path",
                    metavar="directory",
                    nargs="?",
                    default=".",
                    help="where to create this repository.")

# create the repo according to the path given by default it is set to the current directory
# gets called when the init command is called
def cmd_init(args):
  repo_create(args.path)

# recursive function to find the path to the git directory
def repo_find(path=".", required = True):
  # convert the path to the absolute path
  path = os.path.realpath(path)

  # check if the path has a git dir if yes then return the new instance of git repo
  if os.path.isdir(os.path.join(path, ".git")):
    return GitRepository(path)
  
  #go up to the parent directory
  parent = os.path.realpath(os.path.join(path, ".."))

  # if the parent is the same as the path then check if the git directory is required or not
  if parent == path:
    if required:
      raise Exception("No git directory.")
    else:
      return None
    
  # recursive call to find the git dir
  return repo_find(parent, required)

# git object
class GitObject(object):
  # constructor for the git object
  def __init__(self, data=None):
    # if data is not none then deserialize the data else init the object
    if data!=None:
      self.deserialize(data)
    else:
      self.init()
    
  # serialize the object
  def serialize(self, repo):
    raise Exception("Unimplemented!")
  
  # deserialize the object
  def deserialize(self, repo):
    raise Exception("Unimplemented!")
  
  # default pass
  def init(self):
    pass

# function to read the repo and ist SHA1 hash
def object_read(repo, sha):
  # get the path to the object first two bits of the sha hash denote the directory and rest denote the file
  path = repo_file(repo, "objects", sha[0:2], sha[2:])

  # check if the file exists or not
  if not os.path.isfile(path):
    return None
  
  # open the file in read binary mode and decompress the file
  with open(path , "rb") as f:
    raw = zlib.decompress(f.read())

    # find the first space in the file  
    x = raw.find(b' ')
    # get the object type 
    fmt = raw[0:x]

    # find the null byte
    y = raw.find(b'\x100', x)
    # get the size of the object by decoding the ascii value
    size = int(raw[x:y].decode("ascii"))

    # check if the size is equal to the length of the raw file
    if size != len(raw)-y-1:
      raise Exception("Malformed Object {0}: bad length".format(sha))
    
    # match the object type
    match fmt:
      case b'commit' : c=GitCommit
      case b'tree'   : c=GitTree
      case b'tag'    : c=GitTag
      case b'blob'   : c=GitBlob
      case _:
        raise Exception("Unkown type {0} for object {1}".format(fmt.decode("ascii"), sha))
    
    # return the required git object initialized with the data except the header
    return c(raw[y+1:])
  
# function for writing the object to the repo
def object_write(obj, repo=None):
  data = obj.serialize

  # construct the header for the object with its object type, space, length of the data as a string, null byte, and data 
  result = obj.fmt + b' ' + str(len(data)).encode()+ b'\x00' + data

  # compute the sha1 hash of the result into hexadecimal
  sha = hashlib.sha1(result).hexdigest()

  # if repo is provided then write the object to the repo
  if repo:
    # construct the path to the object
    path = repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

    # check if the file exists or not
    if not os.path.exists(path):
      with open(path, 'wb') as f:
        # write the compressed data to the file
        f.write(zlib.compress(result))
  
  # return the sha1 hash of the object
  return sha

#  git blob object
class GitBlob(GitObject):
  # set fmt to blob
  fmt=b'blob'

  # serialize the object by returning the blobdata
  def serialize(self):
    return self.blobdata
  
  # deserialize the object by setting the blobdata to the data
  def deserialize(self, data):
    self.blobdata = data

# catfile command in the cmdline
argsp = argsubparsers.add_parser("cat-file", help="Help provide the details about the contents")

# add the arguments to the cmd of object type and the object itself to display
argsp.add_argument("type",
                   metavar="type",
                   choices=["blob","commit","tag","tree"],
                   help="Specify the type")

argsp.add_argument("object",
                   metavar="object",
                   help="object to display")

# wrapper for the catfile command
def cmd_cat_file(args):
  repo = repo_find()
  cat_file(repo, args.object, fmt=args.type.encode())

# function to display the contents of the object
def cat_file(repo, object, fmt=None):
  obj = object_read(repo, object_find(repo, obj, fmt=fmt))
  sys.stdout.buffer.write(obj.serialize())

# function to find the object
def object_find(repo, name, fmt=None, follow=True):
  return name

# hash-object command in the cmdline
argsp = argsubparsers.add_parser("hash-object", help="Compute object ID and optionally creates a blob from file")

# add the arguments to the cmd of type and write
argsp.add_argument("-t",
                   metavar="type",
                   choices=["blob","commit","tag","tree"],
                    default="blob",
                    help="Specify the type")

argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")

# add path argument
argsp.add_argument("path", help="Read object from <file>")

# wrapper for the hash-object command
def cmd_hash_object(args):
  # find the repo
  if args.write:
    repo = repo_find()
  else: 
    repo = None

  # open the file in read binary mode and compute the sha1 hash of the object and print it
  with open(args.path, "rb") as fd:
    sha = object_hash(fd, args.type.encode(), repo)
    print(sha)

# function to hash the object
def object_hash(fd, fmt, repo=None):
  # read the data from the file
  data = fd.read()

  # match the object type
  match fmt:
    case b'commit' : obj=GitCommit(data)
    case b'tree'   : obj=GitTree(data)
    case b'tag'    : obj=GitTag(data)
    case b'blob'   : obj=GitBlob(data)
    case _: raise Exception("Unknown type %s!" % fmt)
  
  # if repo is provided then write the object to the repo
  return object_write(obj, repo)

# function for key value list mapping
def kvlm_parse(raw, start=0, dct=None):
  # if the dictionary is not provided then create an ordered dictionary
  if not dct:
    dct = collections.OrderedDict()
  # have to declare it attached to the function othrewise all other operations will be done on the same dictionary

  # find the first space and newline in the raw data
  spc = raw.find(b' ', start)
  nl = raw.find(b'\n', start)

  # if no space is found or newline is found before space then add the data to the dictionary
  if(spc < 0) or (nl < spc):
    assert nl == start            # newline is at the start
    dct[None] = raw[start+1:]     # add the data to the dictionary starting from the next character from newline
    return dct 
  
  # get the key starting from the start to the space
  key = raw[start:spc]
  end = start     # set the end to start  

  # loop to process the key value pair
  while True:
    # find the next newline character
    end = raw.find(b'\n', end+1)
    if raw[end+1] != ord(' '): break # if the next character is not a space then break the loop and process the key value pair

  value = raw[spc+1:end].replace(b'\n ',b'\n') # get the value by replacing the newline and space with newline  

  # if the key is already present in the dictionary then append the value to the key
  if key in dct:
    if type(dct[key] == list):
      dct[key].append(value)
    else: 
      dct[key] = [ dct[key], value ]
  else:
    dct[key] = value

  # recursive call to parse the raw data
  return kvlm_parse(raw, start=end+1, dct=dct)

# function to serialize the key value list mapping
def kvlm_serialize(kvlm):
  ret = b''   # initialize the return value to empty byte string

  # loop through the key value list mapping
  for k in kvlm.keys():
    if k == None: continue   # if the key is none then continue
    val = kvlm[k]            # get the value of the key
    if type(val) != list:    # checks if the value is a list or not if not then convert it to a list
      val = [ val ]

    # loop through the values
    for v in val:
      ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'  # append the key value pair to the return value in the format key value newline

  # appends any data under the none key
  ret += b'\n' + kvlm[None] + b'\n'
  
  return ret 

class GitCommit(GitObject):
  # put the format
  fmt =b'commit'

  # deserialize the object
  def deserialize(self, data):
    self.kvlm = kvlm_parse(data)
  
  # serialize the object  
  def serialize(self, repo):
    return kvlm_serialize(self.kvlm)
  
  # constructor function
  def init(self):
    self.kvlm = dict()

# log command in the cmdline
argsp = argsubparsers.add_parser("log", help="Display history of a given commit")

argsp.add_argument("commit",
                    default="HEAD",
                    nargs="?",
                    help="Commit to start at")

def cmd_log(args):
  repo = repo_find()

  # print the graphviz of the log
  print("digraph wyaglog{")
  print("  node[shape=rect]")
  # pass the repo, sha1 hash and a set to keep the record of visited commits
  log_graphviz(repo, object_find(repo, args.commit), set())
  print("}")

def log_graphviz(repo, sha, seen):

  # check if the commit has been visited already
  if sha in seen:
    return
  
  # add the commit to the seen set
  seen.add(sha)

  # get commit object
  commit = object_read(repo, sha)

  # short version of hash for display purposes
  short_hash = sha[0:8]

  # get the commit message from the commit object ans remove any spaces or newlines
  message = commit.kvlm[None].decode("utf8").strip()

  # escape the backslashes and double quotes
  message = message.replace("\\", "\\\\")
  message = message.replace("\"", "\\\"")

  # only take the first line of the message
  if("\n" in message):
    message = message[:message.find("\n")]
    
  # print the commit node with its short hash and message
  print(" c_{0} [label=\"{1}: {2}\"]".format(sha, sha[0:7], message))
  
  # check the format of the commit object for correctness
  assert commit.fmt == b'commit'

  # check for parent
  if not b'parent' in commit.kvlm.keys():
    return
  
  # retrieve the parent commit
  parents = commit.kvlm[b'parent']

  # check if the parent is a list or not
  if type(parents) != list:
    parents = [ parents ]

  # for each parent commit call the log_graphviz function
  for p in parents:
    p = p.decode("ascii")
    print("  c_{0} -> c_{1};".format(sha, p))
    log_graphviz(repo, p, seen)
