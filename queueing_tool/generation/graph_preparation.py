import graph_tool.all as gt
import numpy          as np

def _test_graph(g) :
    if isinstance(g, str) :
        g = gt.load_graph(g, fmt='xml')
    elif not isinstance(g, gt.Graph) :
        raise TypeError("Need to supply a graph-tool graph or the location of a graph")
    return g


def osm_edge_types(g) :
    g = _test_graph(g)

    g.reindex_edges()
    vertex_props = set()
    for key in g.vertex_properties.keys() :
        vertex_props.add(key)

    edge_props = set()
    for key in g.edge_properties.keys() :
        edge_props.add(key)

    has_garage  = 'garage' in vertex_props
    has_destin  = 'destination' in vertex_props
    has_light   = 'light' in vertex_props
    has_egarage = 'garage' in edge_props
    has_edestin = 'destination' in edge_props
    has_elight  = 'light' in edge_props

    vType   = g.new_vertex_property("int")
    eType   = g.new_edge_property("int")
    for v in g.vertices() :
        if has_garage and g.vp['garage'][v] :
            e = g.edge(v,v)
            if isinstance(e, gt.Edge) :
                eType[e]  = 1
            vType[v]    = 1
        if has_destin and g.vp['destination'][v] :
            e = g.edge(v,v)
            if isinstance(e, gt.Edge) :
                eType[e]  = 2
            vType[v]  = 2
        if has_light and g.vp['light'][v] :
            e = g.edge(v,v)
            if isinstance(e, gt.Edge) :
                eType[e]  = 3
            vType[v]  = 3

    for e in g.edges() :
        if has_egarage and g.ep['garage'][e] :
            eType[e]  = 1
        if has_edestin and g.ep['destination'][e] :
            eType[e]  = 2
        if has_elight and g.ep['light'][e] :
            eType[e]  = 3

    g.vp['vType'].a = vType.a + 1
    g.ep['eType'].a = eType.a + 1
    return g


def _calculate_distance(latlon1, latlon2) :
    """Calculates the distance between two points on earth.
    """
    lat1, lon1  = latlon1
    lat2, lon2  = latlon2
    R     = 6371          # radius of the earth in kilometers
    dlon  = lon2 - lon1
    dlat  = lat2 - lat1
    a     = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon/2))**2
    c     = 2 * np.pi * R * np.arctan2( np.sqrt(a), np.sqrt(1-a) ) / 180
    return c


def add_edge_lengths(g) :
    """Add the ``edge_length`` **property_map** to a graph.
    """
    g = _test_graph(g)
    elength   = g.new_edge_property("double")

    for e in g.edges() :
        latlon1     = g.vp['pos'][e.target()]
        latlon2     = g.vp['pos'][e.source()]
        elength[e]  = np.round(_calculate_distance(latlon1, latlon2), 3)
    
    g.ep['edge_length'] = elength
    return g


def random_edge_types(g, pTypes) :
    """Randomly sets edge types of the graph.
    """

    g = _test_graph(g)

    nEdges  = g.num_edges()
    edges   = np.random.shuffle([k for k in range(nEdges)])
    cut_off = np.cumsum( list(pTypes.values()) )

    if np.isclose(cut_off[-1], 1) :
        cut_off = np.round(cut_off * nEdges, out=np.zeros(len(pTypes), int))
    elif cut_off != nEdges :
        raise RuntimeError("pTypes must sum to one, or sum to the number of edges in the graph")

    eTypes  = {}
    for k, key in enumerate(pTypes.keys()) :
        if k == 0 :
            for ei in edges[:cut_off[k]] :
                eTypes[ei] = key
        else :
            for ei in edges[cut_off[k-1]:cut_off[k]] :
                eTypes[ei] = key

    vType = g.new_vertex_property("int")
    eType = g.new_edge_property("int")

    for e in g.edges() :
        eType[e] = eTypes[g.edge_index[e]]
        if e.target() == e.source() :
            vType[e.target()] = eTypes[g.edge_index[e]]
        else :
            vType[e.target()] = 1
    
    g.vp['vType'] = vType
    g.ep['eType'] = eType
    return add_edge_lengths(g)


def pagerank_edge_types(g, pType2=0.1, pType3=0.1) :
    """Sets edge types 2 to the graph using pagerank.
    """
    g = _test_graph(g)

    pagerank    = gt.pagerank(g)
    tmp         = np.sort( np.array(pagerank.a) )
    nDests      = int(np.ceil(g.num_vertices() * pType2))
    dests       = np.where(pagerank.a >= tmp[-nDests])[0]
    
    dest_pos    = np.array([g.vp['pos'][g.vertex(k)] for k in dests])
    nFCQ        = int(pType3 * g.num_vertices())
    min_g_dist  = np.ones(nFCQ) * np.infty
    ind_g_dist  = np.ones(nFCQ, int)
    
    r, theta    = np.random.random(nFCQ) / 500, np.random.random(nFCQ) * 360
    xy_pos      = np.array([r * np.cos(theta), r * np.sin(theta)]).transpose()
    g_pos       = xy_pos + dest_pos[ np.array( np.mod(np.arange(nFCQ), nDests), int) ]
    
    for v in g.vertices() :
        if int(v) not in dests :
            tmp = np.array([_calculate_distance(g.vp['pos'][v], g_pos[k, :]) for k in range(nFCQ)])
            min_g_dist = np.min((tmp, min_g_dist), 0)
            ind_g_dist[min_g_dist == tmp] = int(v)
    
    ind_g_dist  = np.unique(ind_g_dist)
    fcqs        = ind_g_dist[:min( (nFCQ, len(ind_g_dist)) )]
    vType       = g.new_vertex_property("int")

    for v in g.vertices() :
        if int(v) in dests :
            vType[v] = 3
            e = g.add_edge(source=v, target=v)
        elif int(v) in fcqs :
            vType[v] = 2
            e = g.add_edge(source=v, target=v)
    
    g.reindex_edges()
    eType     = g.new_edge_property("int")
    eType.a  += 1

    for v in g.vertices() :
        if vType[v] in [2, 3] :
            e = g.edge(v, v)
            if vType[v] == 2 :
                eType[e] = 2
            else :
                eType[e] = 3
    
    g.vp['vType'] = vType
    g.ep['eType'] = eType
    return add_edge_lengths(g)


def _prepare_graph(g, g_colors, q_cls, q_arg) :
    """Prepare graph for QueueNetwork
    """
    g = _test_graph(g)

    g.reindex_edges()
    vertex_t_color    = g.new_vertex_property("vector<double>")
    vertex_pen_color  = g.new_vertex_property("vector<double>")
    vertex_color      = g.new_vertex_property("vector<double>")
    halo_color        = g.new_vertex_property("vector<double>")
    vertex_t_size     = g.new_vertex_property("double")
    vertex_halo_size  = g.new_vertex_property("double")
    vertex_pen_width  = g.new_vertex_property("double")
    vertex_size       = g.new_vertex_property("double")

    control           = g.new_edge_property("vector<double>")
    edge_color        = g.new_edge_property("vector<double>")
    edge_t_color      = g.new_edge_property("vector<double>")
    edge_width        = g.new_edge_property("double")
    arrow_width       = g.new_edge_property("double")
    edge_length       = g.new_edge_property("double")
    edge_times        = g.new_edge_property("double")
    edge_t_size       = g.new_edge_property("double")
    edge_t_distance   = g.new_edge_property("double")
    edge_t_parallel   = g.new_edge_property("bool")

    vertex_props = set()
    for key in g.vertex_properties.keys() :
        vertex_props.add(key)

    edge_props = set()
    for key in g.edge_properties.keys() :
        edge_props.add(key)

    queues      = _set_queues(g, q_cls, q_arg, 'cap' in vertex_props)
    has_length  = 'edge_length' in edge_props

    if 'pos' not in vertex_props :
        g.vp['pos'] = gt.sfdp_layout(g, epsilon=1e-2, cooling_step=0.95)

    for k, e in enumerate(g.edges()) :
        p2  = np.array(g.vp['pos'][e.target()])
        p1  = np.array(g.vp['pos'][e.source()])
        edge_length[e]  = g.ep['edge_length'][e] if has_length else np.linalg.norm(p1 - p2)
        edge_t_color[e] = [0, 0, 0, 1]
        if e.target() == e.source() :
            edge_color[e] = [0, 0, 0, 0]
        else :
            control[e]    = [0, 0, 0, 0]
            edge_color[e] = queues[k].colors['edge_normal']

    for v in g.vertices() :
        e = g.edge(v, v)
        vertex_t_color[v] = g_colors['text_normal']
        halo_color[v]     = g_colors['halo_normal']
        if isinstance(e, gt.Edge) :
            vertex_pen_color[v] = queues[g.edge_index[e]].current_color(2)
            vertex_color[v]     = queues[g.edge_index[e]].current_color()
        else :
            vertex_pen_color[v] = [0.0, 0.5, 1.0, 1.0]
            vertex_color[v]     = g_colors['vertex_normal'] 

    edge_width.a        = 1.25
    arrow_width.a       = 8
    edge_times.a        = 1
    edge_t_size.a       = 8
    edge_t_distance.a   = 8

    vertex_t_size.a     = 8
    vertex_halo_size.a  = 1.3
    vertex_pen_width.a  = 1.1
    vertex_size.a       = 8

    g.vp['vertex_text_color']     = vertex_t_color
    g.vp['vertex_color']          = vertex_pen_color
    g.vp['vertex_fill_color']     = vertex_color
    g.vp['vertex_halo_color']     = halo_color
    g.vp['vertex_text_position']  = g.new_vertex_property("double")
    g.vp['vertex_font_size']      = vertex_t_size
    g.vp['vertex_halo_size']      = vertex_halo_size
    g.vp['vertex_pen_width']      = vertex_pen_width
    g.vp['vertex_size']           = vertex_size
    g.vp['vertex_text']           = g.new_vertex_property("string")
    g.vp['vertex_halo']           = g.new_vertex_property("bool")

    g.ep['edge_font_size']        = edge_t_size
    g.ep['edge_text_distance']    = edge_t_distance
    g.ep['edge_text_parallel']    = g.new_edge_property("bool")
    g.ep['edge_text_color']       = edge_t_color
    g.ep['edge_text']             = g.new_edge_property("string")
    g.ep['edge_control_points']   = control
    g.ep['edge_color']            = edge_color
    g.ep['edge_pen_width']        = edge_width
    g.ep['edge_length']           = edge_length
    g.ep['edge_marker_size']      = arrow_width
    g.ep['edge_times']            = edge_times
    return g, queues


def _set_queues(g, q_cls, q_arg, has_cap) :
    queues    = [0 for k in range(g.num_edges())]

    for e in g.edges() :
        qedge = (int(e.source()), int(e.target()), g.edge_index[e])
        eType = g.ep['eType'][e]

        if has_cap and 'nServers' not in q_arg[eType] :
            q_arg[eType]['nServers'] = max(g.vp['cap'][e.target()] // 2, 1)

        queues[qedge[2]] = q_cls[eType](edge=qedge, **q_arg[eType])

    return queues