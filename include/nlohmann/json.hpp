// Minimal, dialect-limited replacement for nlohmann::json
// Provides only the functionality required by halfax_kernel_broker.cpp
#pragma once

#include <string>
#include <map>
#include <vector>
#include <cctype>
#include <sstream>
#include <stdexcept>

namespace nlohmann {

struct json {
    enum Type { Null, Object, Array, String, Number };
    Type type = Null;
    std::map<std::string, json> obj;
    std::vector<json> arr;
    std::string str;
    unsigned long num = 0;

    json() : type(Null) {}
    json(const char* s) : type(String), str(s) {}
    json(const std::string& s) : type(String), str(s) {}
    json(unsigned long v) : type(Number), num(v) {}

    static json array() { json j; j.type = Array; return j; }

    bool is_array() const { return type == Array; }
    size_t size() const { return (type==Array)?arr.size():0; }

    json& operator[](size_t i) { return arr.at(i); }
    const json& operator[](size_t i) const { return arr.at(i); }
    json& operator[](const std::string& k) { return obj[k]; }
    const json& operator[](const std::string& k) const {
        auto it = obj.find(k);
        if (it==obj.end()) throw std::out_of_range("key");
        return it->second;
    }

    template<typename T>
    T get() const;

    void push_back(const json& j) { if(type!=Array) throw std::runtime_error("not array"); arr.push_back(j); }

    // allow push_back with initializer list of pairs to create an object
    void push_back(std::initializer_list<std::pair<const std::string, json>> list) {
        json o; o.type = Object;
        for (auto &p : list) o.obj.emplace(p.first, p.second);
        push_back(o);
    }

    // construct object from initializer_list
    json(std::initializer_list<std::pair<const std::string, json>> list) {
        type = Object;
        for (auto &p: list) obj.emplace(p.first, p.second);
    }

    std::string dump() const {
        std::ostringstream o;
        if (type == Object) {
            o << '{';
            bool first=true;
            for (auto &p: obj) {
                if (!first) o << ','; first=false;
                o << '"' << p.first << '"';
                o << ':' << p.second.dump();
            }
            o << '}';
        } else if (type == Array) {
            o << '[';
            for (size_t i=0;i<arr.size();++i) { if (i) o<<','; o << arr[i].dump(); }
            o << ']';
        } else if (type == String) {
            o << '"' << str << '"';
        } else if (type == Number) {
            o << num;
        } else {
            o << "null";
        }
        return o.str();
    }

    // Very small parser tailored to parsing an array of objects with numeric or string values
    static json parse(const std::string &s) {
        size_t i = 0, n = s.size();
        auto skip = [&](void){ while(i<n && isspace((unsigned char)s[i])) ++i; };
        skip();
        if (i>=n || s[i] != '[') throw std::runtime_error("expected [");
        ++i; skip();
        json root = json::array();
        while (i<n) {
            skip();
            if (i<n && s[i] == ']') { ++i; break; }
            if (i<n && s[i] == '{') {
                ++i; skip();
                json obj; obj.type = Object;
                while (i<n) {
                    skip();
                    if (i<n && s[i] == '}') { ++i; break; }
                    // parse string key
                    if (s[i] != '"') throw std::runtime_error("expected key string");
                    ++i; size_t kstart = i;
                    while (i<n && s[i] != '"') ++i;
                    std::string key = s.substr(kstart, i-kstart);
                    ++i; skip(); if (i>=n || s[i] != ':') throw std::runtime_error("expected :"); ++i; skip();
                    // parse value (number or string)
                    if (i<n && s[i]=='"') {
                        ++i; size_t vs = i; while (i<n && s[i] != '"') ++i; std::string val = s.substr(vs, i-vs); ++i;
                        obj.obj.emplace(key, json(val));
                    } else {
                        // number (decimal or 0x hex)
                        size_t vs = i;
                        // accept optional '-' or digits or 0x
                        if (i<n && s[i]=='0' && i+1<n && (s[i+1]=='x' || s[i+1]=='X')) {
                            i += 2; size_t hx = i; while (i<n && isxdigit((unsigned char)s[i])) ++i;
                            std::string hs = s.substr(hx, i-hx);
                            unsigned long v = 0; std::stringstream ss; ss << std::hex << hs; ss >> v; obj.obj.emplace(key, json(v));
                        } else {
                            // decimal
                            while (i<n && (isdigit((unsigned char)s[i]) || s[i]=='-')) ++i;
                            std::string ns = s.substr(vs, i-vs);
                            unsigned long v = 0; if (!ns.empty()) { v = std::stoul(ns); }
                            obj.obj.emplace(key, json(v));
                        }
                    }
                    skip(); if (i<n && s[i] == ',') { ++i; skip(); continue; }
                }
                root.arr.push_back(obj);
                skip(); if (i<n && s[i]==',') { ++i; continue; }
            } else break;
        }
        return root;
    }
};

template<> inline unsigned long json::get<unsigned long>() const {
    if (type == Number) return num;
    if (type == String) return std::stoul(str);
    throw std::runtime_error("not a number");
}

} // namespace nlohmann
