const xmlrpc = require('xmlrpc');
const client = xmlrpc.createSecureClient({ host, path: `/xmlrpc/2/${service}` });
const c2 = xmlrpc.createClient({ host, path: process.env.ODOO_RPC_PATH });
