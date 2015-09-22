import json
import os
import re

try:
	from collections import OrderedDict
except:
	from ordereddict import OrderedDict

import requests
from pyld import jsonld

class LDPResource(object):
	uri = ""
	slug = ""
	data = ""
	link_header = ""
	etag = ""
	contentType = ""
	container = None

	def __init__(self, uri="", slug="", container=None):
		self.uri = uri
		if slug:
			self.slug = slug
		elif uri:
			# split to find the slug
			self.slug = os.path.split(uri)[1]
		self.data = ""		
		self.link_header = ""
		self.links = {}
		self.etag = ""
		self.contentType = ""
		self.container = container		

	def http_setup(self, req, reader=None, target=None):
		self.data = req.content
		self.etag = req.headers.get('etag', '')
		self.link_header = req.headers.get('link', '')
		self.contentType = req.headers.get('content-type', '')

		# XXX Replace with real link header parser
		links = self.link_header.split(', ')
		ldict = {}
		lre = re.compile("<(.+)>;\s*rel\s*=\s*\"(.+)\"")
		for l in links:
			m = lre.match(l)
			if m:
				uri, t = m.groups()
				try:
					ldict[t].append(uri)
				except:
					ldict[t] = [uri]					
		self.links = ldict

	def read(self, filename):
		# Read content in from disk
		# Only useful for first load
		if type(filename) in [str, unicode]:
			fh = file(filename)
		elif filename.read:
			fh = filename
		else:
			raise ValueError()
		self.data = fh.read()
		fh.close()

	def update_etag(self):	
		hdrs = {'Accept': self.contentType}		
		req = requests.head(url=self.uri, headers=hdrs)
		req.raise_for_status()
		self.etag = req.headers['etag']

	def create(self):
		# POST representation to container
		hdrs = {'Content-Type': self.contentType}
		if self.slug:
			hdrs['Slug'] = self.slug

		req = requests.post(url=self.container.uri, data=self.data, headers=hdrs)
		req.raise_for_status()

		status = req.status_code
		resp_headers = req.headers
		self.uri = resp_headers['Location']
		self.etag = resp_headers['etag']

	def update(self):
		if not self.uri:
			raise ValueError()
		hdrs = {'Content-Type': self.contentType}
		if self.etag:
			hdrs['If-Match'] = self.etag
		req = requests.put(url=self.uri, data=self.data, headers=hdrs)
		req.raise_for_status()		

		self.etag = req.headers.get('etag', '')

	def delete(self, tombstone=False):
		if not self.uri:
			raise ValueError()

		if self.etag:
			hdrs={'If-Match': self.etag}
		else:
			hdrs = {}
		req = requests.delete(url=self.uri, headers=hdrs)
		req.raise_for_status()	

		if tombstone:
			# also delete the tombstone associated with this resource
			tomburi = os.path.join(self.uri, "fcr:tombstone")
			req = requests.delete(url=tomburi)
			req.raise_for_status()

	def patch_single(self, field, value):
		if not self.uri:
			raise ValueError()

		if field.find(':') == -1 and self.context.has_key(field):
			# Look in our context
			cf = self.context[field]
			if type(cf) == dict:
				field = cf['@id']
			else:
				field = cf

		if type(value) in [str, unicode]:
			if value.find(' ') > -1 and value[0] != '"':
				# should be a string literal
				value = '"%s"' % value
			elif value.find(' ') == -1 and value.startswith('http'):
				# Should be a uri
				value = '<%s>' % value
		# otherwise use a raw value and hope it's right

		hdrs = {'Content-Type': 'application/sparql-update'}
		if self.etag:
			hdrs['If-Match'] = self.etag

		patch = []
		# Generate prefixes from context
		for pfx,val in self.context.items():
			if type(val) in [str, unicode] and val.startswith('http'):
				patch.append("PREFIX %s: <%s>" % (pfx, val))
		patch.append("")
		patch.append("INSERT {<> %s %s .}" % (field, value))
		patch.append("WHERE {}")
		patchstr = "\n".join(patch)

		req = requests.patch(url=self.uri, data=patchstr, headers=hdrs)
		req.raise_for_status()
		self.etag = req.headers.get('etag', '')


class NonRdfSource(LDPResource):
	_type = "ldp:NonRDFSource"
	describedby = None

	def __init__(self, uri="", slug="", filename="", data=""):
		super(NonRdfSource, self).__init__(uri, slug)		
		self.describedby = None
		if not uri:
			if data:
				self.data = data
			elif filename:
				self.read(filename)

	def http_setup(self, req, reader, target=None):
		super(NonRdfSource, self).http_setup(req, reader, target)
		# Now grab our metadata
		dby = self.links['describedby'][0]
		rdfs = RdfSource(uri=dby)
		self.describedby = reader.retrieve(dby, instance=rdfs, target=self.uri)

class RdfSource(LDPResource):
	_type = "ldp:RDFSource"
	json = {}
	context = {}
	_setup = False

	def __init__(self, uri="", slug="", container=None):
		super(RdfSource, self).__init__(uri=uri, slug=slug, container=container)
		self.json = {}
		self.contentType = 'application/ld+json'
		self._setup = False
		if self._type:
			self.add_field('@type', self._type)

	def http_setup(self, req, reader, target=None):
		super(RdfSource, self).http_setup(req, reader, target)
		if self.data and self.contentType.startswith("application/ld+json"):
			clean_uri = target if target else self.uri
			self.json = reader.clean_jsonld(req.json(), clean_uri)		

	def add_field(self, what, value):
		# ensure non-duplicates
		if self.json.has_key(what):
			if type(self.json[what]) != list:
				if self.json[what] != value:	
					self.json[what] = [self.json[what], value]
			elif not value in self.json[what]:
				self.json[what].append(value)
		else:
			self.json[what] = value

	def build_from_rdf(self, reader):
		# noop ?
		pass

	def setup(self):
		# noop
		self._setup = True

	def to_jsonld(self):
		js = self.json.copy()
		if not js.has_key('@context'):
			if not self.context:
				self.context = self.container.context
			js['@context'] = self.context
		if not js.has_key('@id'):
			# ensure that the URI is null relative for create
			# otherwise it's a blank node
			js['@id'] = ""
		return js

	def create(self):
		if not self.json:
			raise ValueError()
		elif not self.container:
			# Require a container to be created in
			raise ValueError()

		if not self._setup:
			self.setup()

		js = self.to_jsonld()
		jstr = json.dumps(js)
		self.data  = jstr
		super(RdfSource, self).create()

	def update(self):
		if not self.uri:
			raise ValueError()
		elif not self.json:
			raise ValueError()

		js = self.to_jsonld()
		jstr = json.dumps(js)
		self.data = jstr
		super(RdfSource, self).update()


class Container(RdfSource):
	_type = "ldp:Container"
	contains = []
	_contains_map = {}

	def __init__(self, *args, **kw):
		super(Container, self).__init__(*args, **kw)
		self.contains = []
		self._contains_map = {}

	def build_from_rdf(self, reader):
		super(Container, self).build_from_rdf(reader)
		if self.json and self.json.has_key('contains'):
			# And be ready to replace these with real objects later
			self.contains = self.json['contains']

	def create_child(self, what):
		# Given an LDPResource, create it in self
		# by setting self as its container
		what.container = self
		what.create()
		# And add to contains and _contains_map
		self.contains.append(what.uri)
		self._contains_map[what.uri] = what

	def retrieve_children(self, rdr):
		if type(self.contains) == list:
			for uri in self.contains:
				uri = rdr.get_uri(uri)
				yield self.retrieve_child(uri, rdr)
		else:
			yield self.retrieve_child(rdr.get_uri(self.contains), rdr)

	def retrieve_child(self, uri, rdr):
		# Allow passing in slug
		if not uri.startswith(self.uri) and not uri.startswith('http'):
			uri = os.path.join(self.uri, uri)

		if self._contains_map.has_key(uri):
			return self._contains_map[uri]
		elif not uri in self.contains:
			# we don't have that resource as a child
			raise ValueError()

		what = rdr.retrieve(uri)
		self._contains_map[uri] = what
		return what

	def head_children(self, rdr):
		if type(self.contains) == list:
			for uri in self.contains:
				uri = rdr.get_uri(uri)
				yield self.head_child(uri, rdr)
		else:
			yield self.head_child(rdr.get_uri(self.contains), rdr)
	
	def head_child(self, uri, rdr):
		# Allow passing in slug
		if not uri.startswith(self.uri) and not uri.startswith('http'):
			uri = os.path.join(self.uri, uri)

		if self._contains_map.has_key(uri):
			return self._contains_map[uri]
		elif not uri in self.contains:
			# we don't have that resource as a child
			raise ValueError()
		what = rdr.head(uri)
		return what		


class BasicContainer(Container):
	_type = "ldp:BasicContainer"	


class DirectContainer(Container):
	_type = "ldp:DirectContainer"
	membershipResource = None
	hasMemberRelation = ''
	isMemberOfRelation = ''

	def __init__(self, *args, **kw):
		super(DirectContainer, self).__init__(*args, **kw)
		self.membershipResource = ''
		self.hasMemberRelation = ''
		self.isMemberOfRelation = ''

	def to_jsonld(self):
		js = super(DirectContainer, self).to_jsonld()
		js['membershipResource'] = self.membershipResource.uri
		if self.hasMemberRelation:
			js['hasMemberRelation'] = self.hasMemberRelation
		if self.isMemberOfRelation:
			js['isMemberOfRelation'] = self.isMemberOfRelation
		return js

	def build_from_rdf(self, reader):
		super(DirectContainer, self).build_from_rdf(reader)

		if self.json.has_key('membershipResource'):
			uri = reader.get_uri(self.json['membershipResource'])
			self.membershipResource = reader.retrieve(uri)
		if self.json.has_key('hasMemberRelation'):
			self.hasMemberRelation = self.json['hasMemberRelation']
		if self.json.has_key('isMemberOfRelation'):
			self.isMemberOfRelation = self.json['isMemberOfRelation']

	def build_contents(self, reader, recursive=False):
		# retrieve my kids
		# process membershipResource.hasMemberRelation
		prop = reader.property_map.get(self.hasMemberRelation, '')
		# _children is now a generator
		kids = list(self.retrieve_children(reader))
		setattr(self.membershipResource, prop, kids)


class IndirectContainer(DirectContainer):
	_type = "ldp:IndirectContainer"
	insertedContentRelation = ''

	def __init__(self, *args, **kw):
		super(IndirectContainer, self).__init__(*args, **kw)
		self.insertedContentRelation = ''

	def build_from_rdf(self, reader):
		super(IndirectContainer, self).build_from_rdf(reader)
		if self.json.has_key('insertedContentRelation'):
			self.insertedContentRelation = self.json['insertedContentRelation']

	def to_jsonld(self):
		js = super(IndirectContainer, self).to_jsonld()		
		if self.insertedContentRelation:
			js['insertedContentRelation'] = self.insertedContentRelation
		return js

	def build_contents(self, reader, recursive=False):
		# retrieve my kids
		# process membershipResource.hasMemberRelation kid.insertedContentRelation
		myprop = reader.property_map.get(self.hasMemberRelation, '')
		icprop = reader.property_map.get(self.insertedContentRelation, '')
		# a generator...
		kids = self.retrieve_children(reader)
		vals = []
		for k in kids:
			vals.append(getattr(k, icprop))
		setattr(self.membershipResource, myprop, vals)

	
class LDPReader(object):

	def __init__(self, context = None):
		self.ldp_headers_get = {'Accept': 'application/ld+json'}

		cmap = OrderedDict()
		# from worst to best so subclasses can just add

		cmap['ldp:RDFSource'] = RdfSource
		cmap['ldp:NonRDFSource'] = NonRdfSource
		cmap['ldp:Container'] = Container
		cmap['ldp:IndirectContainer'] = IndirectContainer
		cmap['ldp:DirectContainer'] = DirectContainer
		cmap['ldp:BasicContainer'] = BasicContainer
		cmap['IndirectContainer'] = IndirectContainer
		cmap['DirectContainer'] = DirectContainer
		cmap['BasicContainer'] = BasicContainer
		self.class_map = cmap

		self.object_map = {}
		self.property_map = {}

		if context:
			fh = file(context)
			data = fh.read()
			fh.close()
			self.context = json.loads(data)['@context']
		else:
			self.context = {}


	def get_uri(self, uri):
		try:
			return uri['@id']
		except:
			if type(uri) in [str, unicode]:
				return uri
			else:
				print "Looking for a uri, got: %r" % uri
				return None

	def clean_jsonld(self, js, uri):
		if type(js) == list:
			# find actual object
			# NB for fcr:metadata it's not retrieved URI
			for o in js:
				if o['@id'] == uri:
					js = o
					break

		js = jsonld.compact(js, self.context)
		del js['@context']
		return js

	def retrieve(self, uri, instance=None, target=None):

		if self.object_map.has_key(uri):
			return self.object_map[uri]

		print "Fetching: " + uri
		req = requests.get(url=uri, headers=self.ldp_headers_get)
		req.raise_for_status()

		ct = req.headers.get('content-type', '')
		# Find most appropriate @type
		clean_uri = target if target else uri
		if ct.startswith('application/ld+json'):
			# Grab the json and look for classes
			if instance == None:
				js = self.clean_jsonld(req.json(), clean_uri)
				# N.B. stepping through from end to beginning
				for k,v in reversed(self.class_map.items()):
					if k in js['@type']:
						tomake = v
						break
				if tomake == None:
					raise ValueError()

				# make a tomake()
				instance = tomake(uri)
				instance.context = self.context
				self.object_map[uri]= instance
				instance.http_setup(req, self, target=clean_uri)
				instance.build_from_rdf(self)

			else:
				instance.context = self.context
				self.object_map[uri] = instance
				instance.http_setup(req, self, target=clean_uri)
				instance.build_from_rdf(self)

		else:
			# NonRdfSource, make a ldp:NonRdfSource
			instance = NonRdfSource(uri)						
			self.object_map[uri] = instance
			instance.http_setup(req, self)

		return instance

	def head(self, uri, instance=None):
		# Useful if you want to delete stuff with If-Match

		if self.object_map.has_key(uri):
			return self.object_map[uri]

		req = requests.head(url=uri, headers=self.ldp_headers_get)
		req.raise_for_status()

		ct = req.headers.get('content-type', '')
		if ct.startswith('application/ld+json'):
			# Just make an RDFSource as we don't know what else to do
			#    without the content to inspect for @type
			instance = RdfSource(uri)
			instance.context = self.context  # probably unnecessary
			instance.http_setup(req, self)
		else:
			# NonRdfSource, make a ldp:NonRdfSource
			instance = NonRdfSource(uri)						
			instance.http_setup(req, self)

		return instance
