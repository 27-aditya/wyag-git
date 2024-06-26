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

# Git tree leaf -> leaf contains the hash, mode and path
class GitTreeLeaf(self, mode, path, sha):
  def __init__(self, mode, path, sha):
    self.mode = mode
    self.path = path
    self.sha = sha

def tree_parse_one(raw, start=0):
  # find the space to get the mode
  x = raw.find(b' ',start)
  assert x-start == 5 or x-start == 6

  # got the mode
  mode = raw[start:x]
  
  # generalize to length 6 
  if len(raw) == 5:
    mode = b" " + mode

  # find the null byte to get the path
  y = raw.find(b'\x00', x)

  path = raw[x+1:y]

  # get the hash
  sha = format(int.from_bytes(raw[y+1:y+21], "big"), "040x")
  return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

# wrapper for the parse which calls it in a loop
def tree_parse(raw):
  pos = 0
  max = len(raw)
  ret = list()

  while pos < max:
    pos, data = tree_parse_one(raw, pos)
    ret.append(data)

  return ret

# function to check for any same directories with different hashes and convert them into one
def tree_leaf_sort_key(leaf):
  # 10 is vale used to identify directories in unix based systems
  if leaf.mode.startswith(b"10"):
    return leaf.path
  else:
    return leaf.path + "/"
  
# function to serialize a tree object with leaves
def tree_serialize(obj):
  obj.items.sort(key=tree_leaf_sort_key)
  ret = b''

  # make the tuple containing the mode, path and sha
  for i in obj.items:
    ret += i.mode
    ret += b' '
    ret += i.path.endcode("utf8")
    sha = int(i.sha, 16)
    ret += sha.to_bytes(20, byteorder="big")
  
  return ret

# Git tree object    
class GitTree(GitObject):
  fmt = b'tree'

  def deserialize(self, data):
    self.items = tree_parse(data)

  def serialize(self):
    return tree_serialize(self)
  
  def init(self):
    self.items = list()

# ls-tree command
argsp = argsubparsers.add_parser("ls-tree", help="Noice print a tree object.")

argsp.add_argument("-r",
                   dest="recursive",
                   action="store_true",
                   help="Recurse into sub-trees.")

argsp.add_argument("tree",
                   help="The tree object to show.")

# wrapper for the ls-tree command
def cmd_ls_tree(args):
  repo = repo_find()
  ls_tree(repo, args.tree, args.recursive)


def ls_tree(repo, ref, recursive=None, prefix=""):
  # get the hash
  sha = object_find(repo, ref, fmt=b'tree')
  # get the object list
  obj = object_read(repo, sha)

  # loop through the object list
  for item in obj.mode:
    # get the type of the object
    if len(item) == 6:
      type = item[0:2]
    else:
      type = item[0:1]

    # match the type
    match type:
      case b'10': type = "blob"
      case b'04': type = "tree"
      case b'12': type = "blob"
      case b'16': type = "commit"
      case _: raise Exception("Unknown type {}".format(item.mode))

    # print the object recursively
    if not (recursive and type == "tree"):
      print("{0} {1} {2}\t{3}".format(
        "0" * (6 - len(item.mode)) + item.mode.decode("ascii"),
        type,
        item.sha,
        os.path.join(prefix, item.path)))
    else:
       ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

# checkout cmd
argsp = argsubparsers.add_parser("checkout", help="checkout a commit inside of a directory.")

argsp.add_argument("commit",
                   help="The commit or tree to checkout.")

argsp.add_argument("path",
                   help="The EMPTY directory to checkout on.")

# wrapper for the checkout command
def cmd_checkout(args):
  # find the repo
  repo = repo_find()
  
  # get the object
  obj = object_read(repo, object_find(repo, args.commit))

  # if the object is a commit then get the tree object
  if obj.fmt == b'commit':
    obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

  # check if the path exists or not and there is an empty dir present
  if os.path.exists(args.path):
    if not os.path.isdir(args.path):
      raise Exception("Not a directory {}".format(args.path))
    if os.listdir(args.path):
      raise Exception("Not an empty directory {}".format(args.path))
  else:
    os.makedirs(args.path)
  
  # call the ls tree function
  ls_tree(repo, obj, os.path.realpath(args.path))

def ls_tree(repo, tree, path):
  for item in tree.items:
    obj = object_read(repo, item.sha)
    dest = os.path.join(path, item.path)

    if obj.fmt == b'tree':
      os.makedirs(dest)
      ls_tree(repo, obj, path)
    elif obj.fmt == b'blob':
      with open(dest, "wb") as f:
        f.write(obj.blobdata)

# resolve the ref
def ref_resolve(repo, ref):
  path = repo_path(repo, ref) # get the path

  # there may be no commit yet and hence no ref
  if not os.path.isfile(path):
    return None

  with open(path, 'r') as fp:
    data = fp.read()[:-1] # remove the newline
  
  if data.startswith("ref: "):
    return ref_resolve(repo, data[5:])
  else:
    return data

# the references are stored in sorted order by git
def ref_list(repo, path=None):
  if not path:
    path = repo_dir(repo, "refs")
  ret = collections.OrderedDict() #dict to store the references

  for f in sorted(os.listdir(path)):
    can = os.path.join(path, f)
    if os.psth.isdir(can):
      ret[f] = ref_list(repo, can)
    else:
      ref[f] = ref_resolve(repo, can)

  return ret

argsp = argsubparsers.add_parser("show-ref", help="List references.")

def cmd_show_ref(args):
  repo = repo_find()
  refs = ref_list(repo)
  show_ref(repo, refs,with_hash=true, prefix="")

def show_ref(repo, refs, with_hash=True, prefix=""):  
  for k, v in refs.items():
    if(type(v) == str):
      print ("{0}{1}{2}".format(
              v + " " if with_hash else "",
              prefix + "/" if prefix else "",
              k))
    else:
      show_ref(repo, v, with_hash=with_hash, prefix="{0}{1}{2}".format(prefix, "/" if prefix else "", k))

# added the support for tags
class GitTag(GitCommit):
  fmt = b'tag'

# add the tag command
argsp = argsubparsers.add_parser("tag", help="List and create tags")

argsp.add_argument("-a",
                    action="store_true",
                    dest="tag_object",
                    help="Whether to create a tag object")
              
argsp.add_argument("name",
                    help="The name of the tag")
                
argsp.add_argument("object",
                    default="HEAD",
                    nargs="?",
                    help="The object the tag refers to")

def cmd_tag(args):
  repo = repo_find()

  if args.name:
    tag_create(repo, args.name, args.object, type='object' if args.create_tag_object else "ref")
  else:
    refs = ref_list(repo)
    show_ref(repo, refs["tags"], with_hash=False)
  
def tag_create(repo, name, ref, create_tag_object=False):

  sha = object_find(repo, ref)

  if create_tag_object:
    tag = GitTag(repo)
    tag.kvlm = collections.OrderedDict()
    tag.kvlm[b'object'] = sha.encode()
    tag.kvlm[b'type'] = b'commit'
    tag.kvlm[b'tag'] = name.encode()
    tag.kvlm[b'tagger'] = b'Wyag<wyag@example.com>'
    tag.kvlm[None] = b"A tag generated by Wyag, which wont let you customize its message."
    tag_sha = object_write(tag,)
    ref_create(repo, "tags/" + name, tag_sha)

  else:
    ref_create(repo, "tags/" + name, sha)

# write the reference to the repo
def ref_create(repo, ref, sha):
  path = repo_file(repo, "refs/" + ref_name) 
  with open(path, 'w') as fp:
    fp.write(sha + "\n")

def object_resolve(repo, name):

  # search for the object in the repo
  candidates = list()
  hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

  # return null if string not present
  if not name.strip():
    return None

  # check if it is a head
  if name == "HEAD":
    return [ ref_resolve(repo, "HEAD") ]

  # if it is a hex string check for a hash
  if hashRE.match(name):
      name = name.lower()
      prefix = name[0:2]
      path = repo_dir(repo, "objects", prefix, mkdir=False)
      if path:
          rem = name[2:]
          for f in os.listdir(path):
            if f.startswith(rem):
              candidates.append(prefix + f)

  as_tag = ref_resolve(repo, "refs/tags/" + name)
  if as_tag: 
      candidates.append(as_tag)

  as_branch = ref_resolve(repo, "refs/heads/" + name)
  if as_branch: 
    candidates.append(as_branch)

  return candidates

def object_find(repo, name, fmt=None, follow=True):
  sha = object_resolve(repo, name)

  if not sha:
    raise Exception("No such reference {0}.".format(name))

  # if multiple refernces are sent by object resolve then it might be ambiguous
  if len(sha) > 1:
    raise Exception("Ambiguous reference {0}: Candidates are:\n - {1}.".format(name,  "\n - ".join(sha)))

  # get the sha hash
  sha = sha[0]

  # if format not specified then return 
  if not fmt:
    return sha

  # read the object and check the format by accessing the kvlm
  while True:
    obj = object_read(repo, sha)

    if obj.fmt == fmt:
      return sha

    if not follow:
      return None

          # Follow tags
    if obj.fmt == b'tag':
      sha = obj.kvlm[b'object'].decode("ascii")
    elif obj.fmt == b'commit' and fmt == b'tree':
      sha = obj.kvlm[b'tree'].decode("ascii")
    else:
      return None

argsp = argsubparsers.add_parser("rev-parse", help="Parse revision (or other objects) identifiers")

argsp.add_argument("--wyag-type",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default=None,
                   help="Specify the expected type")

argsp.add_argument("name", help="The name to parse")

def cmd_rev_parse(args):
  if args.type:
    fmt = args.type.encode()
  else:
    fmt = None

  repo = repo_find()

  print (object_find(repo, args.name, fmt, follow=True))

class GitIndexEntry(object):
  def __init__(self, ctime=None, mtime=None, dev=None, ino=None, mode_type=None, uid=None, gid=None, fsize=None, sha=None, flag_assume_valid=None, flag_stage=None, name=None):
    self.ctime = ctime # creation time in seconds and nanoseconds
    self.mtime = mtime  # modification time in seconds and nanoseconds
    self.dev = dev # device number
    self.ino = ino # inode number
    self.mode = mode  # mode of the file
    self.uid = uid # user id
    self.gid = gid # user's group id
    self.size = fsize # file size
    self.sha = sha  # hash
    self.flag_assume_valid = flag_assume_valid # assume file is valid 
    self.flag_stage = flag_stage  # stage of the file
    self.name = name  # name of the file


