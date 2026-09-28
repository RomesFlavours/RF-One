// CloudFront Function (cloudfront-js-2.0), viewer-request, on every cache
// behavior of distribution E3MIBLH55LEYD8.
//
// RF-One has one official address, https://rfone.romesflavours.com. A request
// that reaches the distribution through its technical hostname is sent (301)
// to the same path and query string on the official address. Any other Host
// (the official one included) continues unchanged, so the redirect target can
// never redirect again. Origin routing (/tips/*) is not touched.

var OFFICIAL_BASE = 'https://rfone.romesflavours.com';
var TECHNICAL_HOST = 'dn1l56t5jz22u.cloudfront.net';

function queryString(qs) {
    var parts = [];
    for (var name in qs) {
        var param = qs[name];
        var values = param.multiValue ? param.multiValue : [param];
        for (var i = 0; i < values.length; i++) {
            // CloudFront gives `?a` and `?a=` the same empty value; `a=` is
            // what every RF-One app reads identically.
            parts.push(name + '=' + values[i].value);
        }
    }
    return parts.length ? '?' + parts.join('&') : '';
}

function handler(event) {
    var request = event.request;
    var host = request.headers.host ? request.headers.host.value.toLowerCase() : '';
    if (host !== TECHNICAL_HOST) {
        return request;
    }
    return {
        statusCode: 301,
        statusDescription: 'Moved Permanently',
        headers: {
            location: { value: OFFICIAL_BASE + request.uri + queryString(request.querystring) },
            'cache-control': { value: 'no-store' }
        }
    };
}
