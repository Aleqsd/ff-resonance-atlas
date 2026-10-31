// Decode raw BCn/BGRA texture data to PNG (read-only helper).
use std::fs::File;
use std::io::{BufWriter, Read};

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let (inp, w, h, fmt, out) = (&a[1], a[2].parse::<usize>().unwrap(), a[3].parse::<usize>().unwrap(), a[4].as_str(), &a[5]);
    let mut data = Vec::new();
    File::open(inp).unwrap().read_to_end(&mut data).unwrap();
    let mut img = vec![0u32; w * h];
    match fmt {
        "PF_BC7" => texture2ddecoder::decode_bc7(&data, w, h, &mut img).unwrap(),
        "PF_DXT1" => texture2ddecoder::decode_bc1(&data, w, h, &mut img).unwrap(),
        "PF_DXT5" => texture2ddecoder::decode_bc3(&data, w, h, &mut img).unwrap(),
        "PF_BC5" => texture2ddecoder::decode_bc5(&data, w, h, &mut img).unwrap(),
        "PF_B8G8R8A8" => { for i in 0..w * h { img[i] = u32::from_le_bytes([data[4*i], data[4*i+1], data[4*i+2], data[4*i+3]]); } }
        _ => panic!("unsupported {}", fmt),
    }
    // img is BGRA packed u32 (0xAARRGGBB)
    let mut rgba = Vec::with_capacity(w * h * 4);
    for p in img { rgba.extend_from_slice(&[(p >> 16) as u8, (p >> 8) as u8, p as u8, (p >> 24) as u8]); }
    let f = BufWriter::new(File::create(out).unwrap());
    let mut enc = png::Encoder::new(f, w as u32, h as u32);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header().unwrap().write_image_data(&rgba).unwrap();
}
