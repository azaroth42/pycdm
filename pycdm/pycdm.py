
import requests
import json
import os, sys

try:
	from collections import OrderedDict
except:
	from ordereddict import OrderedDict

from pyld import jsonld
import copy

class LDPResource(object):
	_type = "ldp:RDFSource"

	uri = ""
	slug = ""
	json = {}
	data = ""
	context = {}

	def __init__(self, uri="", slug="", container=None):
		self.uri = uri
		if slug:
			self.slug = slug
		elif uri:
			# split to find the slug
			self.slug = os.path.split(uri)[1]
		self.data = ""
		self.json = {}
		self.container = container
		# self.context = self.namespaces.copy()
		self.ldp_headers_post = {'Content-Type':'application/ld+json'}

		self.link_header = ""
		self.etag = ""
		self.contentType = ""
		if self._type:
			self.add_field('@type', self._type)

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
		pass

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

		js = self.to_jsonld()
		jstr = json.dumps(js)

		# POST representation to uri
		uri = self.container.uri
		hdrs = self.ldp_headers_post.copy()
		if self.slug:
			hdrs['Slug'] = self.slug

		req = requests.post(url=uri, data=jstr, headers=hdrs)
		print "uri: %s\nheaders: %r\ndata: %s" % (uri, hdrs,jstr)

		req.raise_for_status()
		status = req.status_code
		resp_headers = req.headers
		resp_data = req.content
		if status == 201:
			self.uri = resp_headers['Location']
			self.etag = resp_headers['etag']

	def update(self):
		pass

	def delete(self):
		if not self.uri:
			raise ValueError()
		else:
			if self.etag:
				hdrs={'If-Match': self.etag}
			else:
				hdrs = {}
			req = requests.delete(url=self.uri, headers=hdrs)
			req.raise_for_status()	


class Container(LDPResource):
	_type = "ldp:Container"
	contains = []
	_contains_map = {}

	def __init__(self, *args, **kw):
		super(Container, self).__init__(*args, **kw)
		self.contains = []
		self._contains_map = {}

	def build_from_rdf(self, reader):
		super(Container, self).build_from_rdf(reader)
		if self.json and self.json.has_key('ldp:contains'):
			# And be ready to replace these with real objects later
			self.contains = self.json[key]

	def create_child(self, what):
		# Given an LDPResource, create it in self
		# by setting self as its container
		what.container = self
		what.create()
		# And add to contains and _contains_map
		self.contains.append(what.uri)
		self._contains_map[what.uri] = what

	def retrieve_child(self, uri, rdr):
		if self._contains_map.has_key(uri):
			return self._contains_map[uri]
		elif not uri in self.contains:
			# we don't have that resource as a child
			raise ValueError()

		what = rdr.retrieve(uri)
		self._contains_map[uri] = what
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
		js['ldp:membershipResource'] = self.membershipResource.uri
		if self.hasMemberRelation:
			js['ldp:hasMemberRelation'] = self.hasMemberRelation
		if self.isMemberOfRelation:
			js['ldp:isMemberOfRelation'] = self.isMemberOfRelation
		return js

	def build_from_rdf(self, reader):
		super(DirectContainer, self).build_from_rdf(reader)

		if self.json.has_key('ldp:membershipResource'):
			uri = self.json['ldp:membershipResource']
			self.membershipResource = reader.retrieve(uri)
		if self.json.has_key('ldp:hasMemberRelation'):
			self.hasMemberRelation = self.json['ldp:hasMemberRelation']
		if self.json.has_key('ldp:isMemberOfRelation'):
			self.isMemberOfRelation = self.json['ldp:isMemberOfRelation']


class IndirectContainer(DirectContainer):
	_type = "ldp:IndirectContainer"
	insertedContentRelation = ''

	def __init__(self, *args, **kw):
		super(IndirectContainer, self).__init__(*args, **kw)
		self.insertedContentRelation = ''

	def build_from_rdf(self, reader):
		super(IndirectContainer, self).build_from_rdf(reader)
		if self.json.has_key('ldp:insertedContentRelation'):
			self.insertedContentRelation = self.json['ldp:insertedContentRelation']

	def to_jsonld(self):
		js = super(IndirectContainer, self).to_jsonld()		
		if self.insertedContentRelation:
			js['ldp:insertedContentRelation'] = self.insertedContentRelation
		return js

class NonRDFSource(LDPResource):
	_type = "ldp:NonRDFSource"

	def __init__(self, uri="", slug="", filename="", data=""):
		super(NonRDFSource, self).__init__(uri, slug)		
		if not uri:
			if data:
				self.data = data
			elif filename:
				self.read(filename)


# PCDM resources contain containers
class PcdmResource(Container):
	members = []
	membersContainer = None
	relatedObjects = []
	relatedObjectsContainer = None
	_proxyHash = {}

	def __init__(self, uri="", slug=""):
		self._proxyHash = {}
		# members = list of Proxy objects
		self.members = []
		self.related_objects = []
		self.membersContainer = None
		self.relatedObjectsContainer = None
		super(PcdmResource, self).__init__(uri, slug)

	def build_from_rdf(self, reader):
		# Check if members in contains
		super(PcdmResource, self).build_from_rdf(reader)

		membersuri = os.path.join(self.uri, 'members')
		relateduri = os.path.join(self.uri, 'relatedObjects')

		members = reader.retrieve(membersuri)
		relatedObjects = reader.retrieve(relateduri)
		members.build()
		relatedObjects.build()
		self.membersContainer = members
		self.relatedObjectsContainer = relatedObjects

	# post init, do setup if going to do create
	def setup(self):
		# create the containers
		members = IndirectContainer(slug='members')
		# this is '' before self is created ...
		members.membershipResource = self
		members.hasMemberRelation = 'pcdm:hasMember'
		members.insertedContentRelation = 'ore:proxyFor'
		self.membersContainer = members

		relatedObjects = IndirectContainer(slug='relatedObjects')
		relatedObjects.membershipResource = self
		relatedObjects.hasMemberRelation = 'pcdm:hasRelatedObject'
		relatedObjects.insertedContentRelation = 'ore:proxyFor'		
		self.relatedObjectsContainer = relatedObjects

	def create(self):
		super(PcdmResource, self).create()
		self.create_child(self.membersContainer)
		self.create_child(self.relatedObjectsContainer)

	def add_member(self, what): 
		# Create & return the proxy for the member object/collection
		p = Proxy(slug=what.slug, proxy_for = what, proxy_in = self)
		self.members.append(p)
		self._proxyHash[what] = p
		return p

	def remove_member(self, what):
		# Could be proxy or object
		pass

	def add_related_object(self, what):
		pass

	def remove_related_object(self, what):
		# Could be proxy or object
		pass

	# NB only gets the most recent proxy for what
	# as if what appears multiple times, the proxyHash entry
	# is overwritten
	def get_proxy(self, what):
		return self._proxyHash[what]

	def set_first(self, what):
		if not type(what) == Proxy:
			what = self.get_proxy(what)
		self.first = what

	def get_first(self, what):
		return self.first.proxy_for

	def set_last(self, what):
		if not type(what) == Proxy:
			what = self.get_proxy(what)
		self.last = what

	def get_last(self, what):
		return self.last.proxy_for


class Collection(PcdmResource):
	_type = "pcdm:Collection"
	pass

class Object(PcdmResource):
	_type = "pcdm:Object"
	files = []
	filesContainer = None
	related_files = []
	relatedFilesContainer = None

	def __init__(self, uri="", slug="", ordered=False):
		super(Object, self).__init__(uri=uri, slug=slug)
		# files / related_files are pcdm:File objects
		self.files = []
		self.related_files = []

	def build_from_rdf(self, reader):
		super(Object, self).build()
		# Check if members in contains
		filesuri = os.path.join(self.uri, 'files')
		relatedfilesuri = os.path.join(self.uri, 'relatedFiles')
		filesc = reader.retrieve(filesuri)
		relatedfilesc = reader.retrieve(relatedfilesuri)
		filesc.build()
		relatedfilesc.build()
		self.filesContainer = filesc
		self.relatedFilesContainer = relatedfilesc

	def setup(self):
		# create the containers
		filesc = DirectContainer(slug='files')
		filesc.membershipResource = self
		filesc.hasMemberRelation = 'pcdm:hasFile'
		self.filesContainer = filesc
		relatedfilesc = DirectContainer(slug='relatedFiles')
		relatedfilesc.membershipResource = self
		relatedfilesc.hasMemberRelation = 'pcdm:hasRelatedFile'
		self.relatedFilesContainer = relatedfilesc

	def create(self):
		super(Object, self).create()
		self.create_child(self.filesContainer)
		self.create_child(self.relatedFilesContainer)

	def add_file(self, what):
		pass

	def remove_file(self, what):
		pass

	def add_related_file(self, what):
		pass

	def remove_related_file(self, what):
		pass

class Proxy(LDPResource):
	_type = "ore:Proxy"
	proxy_for=None
	proxy_in= None
	next = None
	prev = None

	def __init__(self, uri="", slug="", proxy_for=None, proxy_in=None):
		self.proxy_for = proxy_for
		self.proxy_in = proxy_in
		super(Proxy, self).__init__(uri, slug)

	# Must be Proxy
	def set_next(self, what):
		self.assert_is(what, Proxy)
		self.next = what
		what.set_prev(self)

	def set_prev(self, what):
		self.assert_is(what, Proxy)
		self.prev = what
		what.set_next(self)


class File(NonRDFSource):
	pass
	


class LDPReader(object):

	def __init__(self):
		self.ldp_headers_get = {'Accept': 'application/ld+json'}

		self.namespaces = {
			"dc": "http://purl.org/dc/elements/1./",
			"dcterms": "http://purl.org/dc/terms/",
			"foaf": "http://xmlns.com/foaf/0.1/",
			"rdfs": "http://www.w3.org/2000/01/rdf-schema#",
			"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
			"ldp": "http://www.w3.org/ns/ldp#",
			"pcdm": "http://pcdm.org/models#",
			"ore": "http://www.openarchives.org/ore/terms/",
			"oa": "http://www.w3.org/ns/oa#",	
        	"exif": "http://www.w3.org/2003/12/exif/ns#",
            "owl": 'http://www.w3.org/2002/07/owl#',
            "skos": 'http://www.w3.org/2004/02/skos/core#',
            "prov": 'http://www.w3.org/ns/prov#',
            "sc": 'http://iiif.io/api/presentation/2#',
            "svcs": 'http://rdfs.org/sioc/services#',
            "iana": 'http://www.iana.org/assignments/relation/',

			"nt": "http://www.jcp.org/jcr/nt/1.0",
			"test": "<info:fedora/test/",
			"fedoraconfig": "http://fedora.info/definitions/v4/config#",
			"image": "http://www.modeshape.org/images/1.0",
			"xs": "http://www.w3.org/2001/XMLSchema",
			"xml": "http://www.w3.org/XML/1998/namespace",
			"mix": "http://www.jcp.org/jcr/mix/1.0",
			"premis": "http://www.loc.gov/premis/rdf/v1#",
			"mode": "http://www.modeshape.org/1.0",
			"sv": "http://www.jcp.org/jcr/sv/1.0",
			"fedora": "http://fedora.info/definitions/v4/repository#",
			"xsi": "http://www.w3.org/2001/XMLSchema-instance",
			"jcr": "http://www.jcp.org/jcr/"
		}
		cmap = OrderedDict()
		# from best to worst so we can iter through it
		cmap['pcdm:Object'] = Object
		cmap['pcdm:Collection'] = Collection
		cmap['ore:Proxy'] = Proxy
		cmap['ldp:IndirectContainer'] = IndirectContainer
		cmap['ldp:DirectContainer'] = DirectContainer
		cmap['ldp:BasicContainer'] = BasicContainer
		cmap['ldp:Container'] = Container
		cmap['ldp:RDFSource'] = LDPResource
		self.class_map = cmap

		self.object_map = {}

	def clean_f4(self, js, uri):
		# strip out random F4 nonsense
		if type(js) == list:
			# find actual object
			for o in js:
				if o['@id'] == uri:
					js = o
					break
		keys = js.keys()
		for k in keys:
			if k.startswith(self.namespaces['fedora']) or k.startswith(self.namespaces['fedoraconfig']):
				del js[k]
		types = js.get('@type', [])
		if types:
			nt = []
			for t in types:
				if not t.startswith(self.namespaces['jcr']) and not t.startswith(self.namespaces['mode']):
					nt.append(t)
			js['@type'] = nt

		# Now compact it
		js = jsonld.compact(js, self.namespaces)
		del js['@context']
		return js

	def retrieve(self, uri):
		req = requests.get(url=uri, headers=self.ldp_headers_get)
		req.raise_for_status()

		link_header = req.headers.get('link', '')
		etag = req.headers.get('etag', '')
		mime = req.headers.get('content-type', '')

		# XXX allow NonRDFSource
		data = req.content
		if mime == "application/ld+json":
			js = self.clean_f4(req.json(), uri)
		else:
			# Should we look at fcr:metadata?
			js = {}

		# Find most appropriate @type
		tomake = None
		for k,v in self.class_map.items():
			if k in js['@type']:
				tomake = v
				break

		if tomake:
			# make a v()
			what = v(uri)
			# Record it so we can look it up later
			self.object_map[uri]= what
			what.etag = etag
			what.link = link_header
			what.contentType = mime
			what.data = data
			what.json = js
			what.context = self.namespaces
			what.context['ldp:hasMemberRelation'] = {'@type': '@id'}
			what.context['ldp:isMemberOfRelation'] = {'@type': '@id'}
			what.context['ldp:membershipResource'] = {'@type': '@id'}
			what.context['ldp:insertedContentRelation'] = {'@type': '@id'}
			try:
				what.build_from_rdf(self)
			except:
				pass
		else:
			raise ValueError()

		return what



fedora4base = "http://localhost:8080/rest/"
reader = LDPReader()
base = reader.retrieve(fedora4base)


def test_postcard():
        c = Collection(slug='Postcards')
        c.setup()
        c.add_field('dc:title', "Postcards Collection")
        base.create_child(c)

        pc = Object(slug='Postcard')
        pc.setup()
        pc.add_field('dc:title', 'Postcard')
        base.create_child(pc)
        #c.add_member(pc)

        #front = Object(slug='Front')
        #pc.add_member(front)
        #back = Object(slug='Back')
        #pc.add_member(back)

        #pf = pc.set_first(front)
        #pb = pc.set_last(back)
        #pf.set_next(pb)

        #ff = File(slug="front.jpg")
        #front.add_file(ff)
        #bf = File(slug="back.jpg")
        #back.add_file(bf)

