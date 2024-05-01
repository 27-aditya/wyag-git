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

argparser = argparse.ArgumentParser(description="Stupid content tracker")

argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

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

class GitRepository(object):
  """A Git Repository"""

  worktree = None
  gitdir = None
  conf = None

  def __init__(self, path, force=False):
    self.worktree = path
    self.gitdir = os.path.join(path, ".git")

    if not (force or os.path.isdir(self.gitdir)):
      raise Exception("Not a Git repository %s" %path)
    
    #Read configuration file in .git/config
    self.conf = configparser.ConfigParser()
    cf = repo_file(self, "config")

    if cf and os.path.exists(cf):
      self.conf.read([cf])
    elif not force:
      raise Exception("Config file missing")
    
    if not force:
      vers = int(self.conf.get("core", "repositoryformatversion"))
      if vers != 0:
        raise Exception("Unsupported repository version %s" %vers)
      
def repo_path(repo, *path):
  """Compute path under repo's gitdir"""
  return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
  """Same as repo_path, but create dirname(*path) if absent, For example,
  repo_file(r, \"refs\", \"remotes\", \"origin\". \"HEAD"\) will create
  .git/ref/remotes/origin."""

  if repo_dir(repo, *path[:-1], mkdir=mkdir):
    return repo_path(repo, *path)
  
def repo_dir(repo, *path, mkdir=False):
  """Same as repo_path, but mkdir *path if absent if mkdir."""

  path = repo_path(repo, *path)

  if os.path.exists(path):
    if (os.dir.path(path)): 
      return path
    else:
      raise Exception("Not a directory path %s" %path)
    
  if mkdir:
    os.makedirs(path)
    return path
  else: 
    return None

def repo_create(path):
  """Create a new repository at path"""

  repo = GitRepository(path, true)

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
