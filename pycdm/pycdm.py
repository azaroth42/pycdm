
import os
from ldp import Container, DirectContainer, IndirectContainer, RDFSource, NonRDFSource, LDPReader

class PcdmReader(LDPReader):
	def __init__(self, context = None):
		super(PcdmReader, self).__init__(context)

		cmap = self.class_map

		cmap['pcdm:File'] = NonRDFSource
		cmap['pcdm:Object'] = Object
		cmap['pcdm:Collection'] = Collection		
		cmap['ore:Proxy'] = Proxy
		cmap['File'] = NonRDFSource
		cmap['Collection'] = Collection
		cmap['Proxy'] = Proxy
		cmap['Object'] = Object

		# in/direct container predicate to object property
		self.property_map = {
			"pcdm:hasMember" : "members",
			"pcdm:hasRelatedObject": "relatedObjects",
			"pcdm:hasFile": "files",
			"pcdm:hasRelatedFile": "relatedFiles",
			"ore:proxyFor": "proxy_for"
		}

# PCDM resources contain containers and have members
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
		super(PcdmResource, self).setup()
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

	def build_contents(self, reader, recursive=False):

		self.membersContainer.build_contents(reader, recursive)
		if recursive:
			for m in self.members:
				m.build_contents(reader, recursive)
		self.relatedObjectsContainer.build_contents(reader, recursive)
		if recursive:
			for m in self.relatedObjects:
				m.build_contents(reader, recursive)

		# XXX Order dependent on update capability
		if self.ordered:
			f = self.json['first']


	def to_jsonld(self):
		js = super(PcdmResource, self).to_jsonld()

		if self.ordered and self.members:
			js['first'] = self.get_proxy(self.members[0]).uri
			js['last'] = self.get_proxy(self.members[-1]).uri
		return js

	def create(self):
		super(PcdmResource, self).create()
		self.create_child(self.membersContainer)
		self.create_child(self.relatedObjectsContainer)
		self.update_etag()
		self.patch_single("memberContainer", self.membersContainer.uri)
		self.patch_single("relatedContainer", self.relatedObjectsContainer.uri)

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
			# We're already in members, note
			if len(self.members) > 1:
				prev = self._proxyHash[self.members[-1]]
				prev.next = p
				p.prev = prev

		self.membersContainer.create_child(p)
		return p

	def remove_member(self, what):
		# XXX Could be proxy or object
		pass

	def add_related_object(self, what):
		pass

	def remove_related_object(self, what):
		# XXX Could be proxy or object
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
		# files are pcdm:File objects
		self.files = []

	def build_from_rdf(self, reader):
		super(Object, self).build_from_rdf(reader)
		# Check if members in contains
		filesuri = os.path.join(self.uri, 'files')
		filesc = reader.retrieve(filesuri)
		self.filesContainer = filesc

	def build_contents(self, reader, recursive=False):
		super(Object, self).build_contents(reader, recursive)
		self.filesContainer.build_contents(reader, recursive)

	def setup(self):
		# create the containers
		super(Object, self).setup()
		filesc = DirectContainer(slug='files')
		filesc.membershipResource = self
		filesc.hasMemberRelation = 'pcdm:hasFile'
		self.filesContainer = filesc

	def create(self):
		super(Object, self).create()
		self.create_child(self.filesContainer)
		self.update_etag()
		self.patch_single('fileContainer', self.filesContainer.uri)

	def add_file(self, what):
		self.filesContainer.create_child(what)
		# Create a specific DirectContainer to manipulate 

	def remove_file(self, what):
		pass


class Proxy(RDFSource):
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
			js['proxyFor'] = self.proxy_for.uri
		if self.proxy_in:
			js['proxyIn'] = self.proxy_in.uri
		if self.next:
			js['next'] = self.next.uri
		if self.prev:
			js['prev'] = self.prev.uri
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


class File(NonRDFSource):
	pass
