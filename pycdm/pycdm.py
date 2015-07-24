
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
		self.etag = ""
		self.contentType = ""
		self.container = container		

	def http_setup(self, req, reader=None):
		self.data = req.content
		self.etag = req.headers.get('etag', '')
		self.link = req.headers.get('link', '')
		self.contentType = req.headers.get('content-type', '')

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
		hdrs = {'Content-Type': self.contentType}
		if self.etag:
			hdrs['If-Match'] = self.etag
		req = requests.put(url=self.uri, headers=hdrs)
		req.raise_for_status()		

	def delete(self, tombstone=False):
		if not self.uri:
			raise ValueError()
		else:
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

class NonRdfSource(LDPResource):
	_type = "ldp:NonRDFSource"

	def __init__(self, uri="", slug="", filename="", data=""):
		super(NonRdfSource, self).__init__(uri, slug)		
		if not uri:
			if data:
				self.data = data
			elif filename:
				self.read(filename)

class RdfSource(LDPResource):
	_type = "ldp:RDFSource"
	json = {}
	context = {}

	def __init__(self, uri="", slug="", container=None):
		super(RdfSource, self).__init__(uri=uri, slug=slug, container=container)
		self.json = {}
		self.contentType = 'application/ld+json'
		if self._type:
			self.add_field('@type', self._type)

	def http_setup(self, req, reader):
		super(RdfSource, self).http_setup(req, reader)
		if self.contentType.startswith("application/ld+json"):
			self.json = reader.clean_f4(req.json(), self.uri)		

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
		kids = []
		if type(self.contains) == list:
			for uri in self.contains:
				uri = rdr.get_uri(uri)
				kids.append(self.retrieve_child(uri, rdr))
		else:
			kids.append(self.retrieve_child(rdr.get_uri(self.contains), rdr))
		return kids

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

		if self.json.has_key('membershipResource'):
			uri = reader.get_uri(self.json['membershipResource'])
			self.membershipResource = reader.retrieve(uri)
		if self.json.has_key('hasMemberRelation'):
			self.hasMemberRelation = self.json['hasMemberRelation']
		if self.json.has_key('isMemberOfRelation'):
			self.isMemberOfRelation = self.json['isMemberOfRelation']

	def build_contents(self, reader):
		# retrieve my kids
		# process membershipResource.hasMemberRelation
		prop = reader.property_map.get(self.hasMemberRelation, '')
		kids = self.retrieve_children(reader)
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
			js['ldp:insertedContentRelation'] = self.insertedContentRelation
		return js

	def build_contents(self, reader):
		# retrieve my kids
		# process membershipResource.hasMemberRelation kid.insertedContentRelation
		myprop = reader.property_map.get(self.hasMemberRelation, '')
		icprop = reader.property_map.get(self.insertedContentRelation, '')
		kids = self.retrieve_children(reader)
		vals = []
		for k in kids:
			vals.append(getattr(k, icprop))
		setattr(self.membershipResource, myprop, vals)

# PCDM resources contain containers
class PcdmResource(Container):
	members = []
	membersContainer = None
	relatedObjects = []
	relatedObjectsContainer = None
	_proxyHash = {}
	ordered = False

	def __init__(self, uri="", slug="", ordered=False):
		self._proxyHash = {}
		# members = list of Proxy objects
		self.members = []
		self.related_objects = []
		self.membersContainer = None
		self.relatedObjectsContainer = None
		self.ordered = ordered
		super(PcdmResource, self).__init__(uri, slug)

	def build_from_rdf(self, reader):
		# Check if members in contains
		super(PcdmResource, self).build_from_rdf(reader)

		membersuri = os.path.join(self.uri, 'members')
		relateduri = os.path.join(self.uri, 'relatedObjects')

		members = reader.retrieve(membersuri)
		relatedObjects = reader.retrieve(relateduri)
		self.membersContainer = members
		self.relatedObjectsContainer = relatedObjects

		if self.json.has_key('first'):
			self.ordered = True

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

	def to_jsonld(self):
		js = super(PcdmResource, self).to_jsonld()
		if self.ordered and self.members:
			js['iana:first'] = self.get_proxy(self.members[0])
			js['iana:last'] = self.get_proxy(self.members[-1])
		return js

	def create(self):
		super(PcdmResource, self).create()
		self.create_child(self.membersContainer)
		self.create_child(self.relatedObjectsContainer)

	def add_member(self, what): 
		# Create & return the proxy for the member object/collection
		p = Proxy(slug=what.slug+"_proxy")
		p.proxy_for = what
		p.proxy_in = self		
		# members is authoritative for first/last
		self.members.append(what)
		self._proxyHash[what] = p

		if self.ordered:
			# manipulate the object list
			if self.members:
				prev = self._proxyHash[self.members[-1]]
				prev.next = p
				p.prev = prev

		self.membersContainer.create_child(p)
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
		super(Object, self).__init__(uri=uri, slug=slug, ordered=ordered)
		# files / related_files are pcdm:File objects
		self.files = []
		self.related_files = []

	def build_from_rdf(self, reader):
		super(Object, self).build_from_rdf(reader)
		# Check if members in contains
		filesuri = os.path.join(self.uri, 'files')
		relatedfilesuri = os.path.join(self.uri, 'relatedFiles')
		filesc = reader.retrieve(filesuri)
		relatedfilesc = reader.retrieve(relatedfilesuri)
		self.filesContainer = filesc
		self.relatedFilesContainer = relatedfilesc

	def setup(self):
		# create the containers
		super(Object, self).setup()
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
		self.filesContainer.create_child(what)

	def remove_file(self, what):
		pass

	def add_related_file(self, what):
		pass

	def remove_related_file(self, what):
		pass

class Proxy(RdfSource):
	_type = "ore:Proxy"
	proxy_for=None
	proxy_in= None
	next = None
	prev = None

	def __init__(self, uri="", slug=""):
		self.proxy_for = None
		self.proxy_in = None
		super(Proxy, self).__init__(uri, slug)

	def to_jsonld(self):
		js = super(Proxy, self).to_jsonld()
		if self.proxy_for:
			js['ore:proxyFor'] = self.proxy_for.uri
		if self.proxy_in:
			js['ore:proxyIn'] = self.proxy_in.uri
		if self.next:
			js['iana:next'] = self.next.uri
		if self.prev:
			js['iana:prev'] = self.prev.uri
		return js

	def set_proxy_for(self, what):
		pass
	def set_proxy_in(self, what):
		pass

	def build_from_rdf(self, reader):
		super(Proxy, self).build_from_rdf(reader)
		self.proxy_for = reader.retrieve(self.json['proxyFor'])
		self.proxy_in = reader.retrieve(self.json['proxyIn'])		

	# Must be Proxy
	def set_next(self, what):
		self.assert_is(what, Proxy)
		self.next = what
		what.set_prev(self)

	def set_prev(self, what):
		self.assert_is(what, Proxy)
		self.prev = what
		what.set_next(self)


class File(NonRdfSource):
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
		cmap['Object'] = Object
		cmap['Collection'] = Collection
		cmap['pcdm:Object'] = Object
		cmap['pcdm:Collection'] = Collection
		cmap['Proxy'] = Proxy		
		cmap['ore:Proxy'] = Proxy
		cmap['IndirectContainer'] = IndirectContainer
		cmap['DirectContainer'] = DirectContainer
		cmap['BasicContainer'] = BasicContainer
		cmap['ldp:IndirectContainer'] = IndirectContainer
		cmap['ldp:DirectContainer'] = DirectContainer
		cmap['ldp:BasicContainer'] = BasicContainer
		cmap['ldp:Container'] = Container
		cmap['ldp:RDFSource'] = RdfSource
		cmap['ldp:NonRDFSource'] = NonRdfSource
		cmap['pcdm:File'] = NonRdfSource
		cmap['File'] = NonRdfSource
		self.class_map = cmap
		self.object_map = {}

		# in/direct container predicate to object property
		self.property_map = {
			"pcdm:hasMember" : "members",
			"pcdm:hasRelatedObject": "relatedObjects",
			"pcdm:hasFile": "files",
			"pcdm:hasRelatedFile": "relatedFiles",
			"ore:proxyFor": "proxy_for"
		}

		fh = file('context.json')
		data = fh.read()
		fh.close()
		self.context = json.loads(data)

	def get_uri(self, uri):
		try:
			return uri['@id']
		except:
			if type(uri) in [str, unicode]:
				return uri
			else:
				print "Got: %r" % uri
				return None

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
		js = jsonld.compact(js, self.context)
		del js['@context']
		return js

	def retrieve(self, uri, instance=None):
		print "Getting: " + uri

		if self.object_map.has_key(uri):
			return self.object_map[uri]

		req = requests.get(url=uri, headers=self.ldp_headers_get)
		req.raise_for_status()

		ct = req.headers.get('content-type', '')
		# Find most appropriate @type
		if ct.startswith('application/ld+json'):
			# Grab the json and look for classes
			if instance == None:
				js = self.clean_f4(req.json(), uri)
				for k,v in self.class_map.items():
					if k in js['@type']:
						tomake = v
						break
				if tomake == None:
					raise ValueError()

				# make a tomake()
				instance = tomake(uri)
				instance.context = self.context
				self.object_map[uri]= instance
				instance.http_setup(req, self)
				try:
					instance.build_from_rdf(self)
				except:
					raise
		else:
			# NonRdfSource
			instance = File(uri)						
			self.object_map[uri] = instance
			instance.http_setup(req, self)
			# And where does our metadata live?

		return instance

fedora4base = "http://localhost:8080/rest/"
reader = LDPReader()
base = reader.retrieve(fedora4base)

def clean_postcard():
	slugs = ['Postcards', 'Postcard', 'Front', 'Back']
	for s in slugs:
		uri = os.path.join(fedora4base, s)
		req = requests.delete(uri)
		try:
			req.raise_for_status()
			uri2 = os.path.join(uri, 'fcr:tombstone')
			req = requests.delete(uri2)	
		except:
			pass


def test_postcard():
    c = Collection(slug='Postcards')
    c.setup()
    c.add_field('dc:title', "Postcards Collection")
    base.create_child(c)

    pc = Object(slug='Postcard')
    pc.setup()
    pc.add_field('dc:title', 'Postcard')
    base.create_child(pc)    
    pcp = c.add_member(pc)

    front = Object(slug='Front', ordered=True)
    front.setup()
    base.create_child(front)
    pc.add_member(front)

    back = Object(slug='Back')
    back.setup()
    base.create_child(back)
    pc.add_member(back)

    ff = File(slug="front.jpg", filename="../front.jpg")
    ff.contentType = "image/jpeg"
    front.add_file(ff)

    bf = File(slug="back.jpg", filename="../back.jpg")
    bf.contentType = "image/jpeg"
    back.add_file(bf)

    return c

def build_postcard():
	c = reader.retrieve(fedora4base + "Postcards")
	c.membersContainer.build_contents(reader)
	for m in c.members:
		# m is a Postcard Object
		m.membersContainer.build_contents(reader)
		for n in m.members:
			# n is a front/back Object
			n.filesContainer.build_contents(reader)

