// Read-only: decompress IoStore blocks listed on stdin ("offset csize usize method" per line) from a .ucas file.
use std::fs::File;
use std::io::{BufRead, Read, Seek, SeekFrom, Write};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut ucas = File::open(&args[1]).expect("open ucas");
    let mut out = File::create(&args[2]).expect("create out");
    let mut ex = oozextract::Extractor::new();
    for line in std::io::stdin().lock().lines() {
        let line = line.unwrap();
        let v: Vec<u64> = line.split_whitespace().map(|x| x.parse().unwrap()).collect();
        if v.len() < 4 { continue; }
        let (off, csz, usz, m) = (v[0], v[1] as usize, v[2] as usize, v[3]);
        let mut cbuf = vec![0u8; csz];
        ucas.seek(SeekFrom::Start(off)).unwrap();
        ucas.read_exact(&mut cbuf).unwrap();
        if m == 0 {
            out.write_all(&cbuf[..usz]).unwrap();
        } else {
            let mut ubuf = vec![0u8; usz];
            let n = ex.read_from_slice(&cbuf, &mut ubuf).expect("decompress");
            out.write_all(&ubuf[..n]).unwrap();
        }
    }
}
