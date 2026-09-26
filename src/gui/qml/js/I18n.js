.pragma library

// Replaces {placeholder} tokens in a localized template string with values
// from params, e.g. format("Page {page} of {total}", {page: 1, total: 5}).
function format(template, params) {
    if (!template) return ""
    return template.replace(/\{(\w+)\}/g, function (match, key) {
        return (params && key in params) ? String(params[key]) : match
    })
}
