import asn1tools
from utils import x509
from utils import io
from utils import misc
from utils import crypto

VALID_ASN_FILE = 'valid.asn'
EXPORTED_KEY_NAME = 'key.pem'
EXPORTED_CHAIN_NAME = 'chain.pem'
EXPORTED_CRL_NAME = 'crl.der'


def main():
    args = misc.parse_arguments()

    # Compile the ASN.1 specification
    asn = asn1tools.compile_files(args.asn_dir + VALID_ASN_FILE, 'der')

    # Import the root private key and cert
    root_privkey = io.import_rsa_private_key(args.root_key_file)
    root_pubkey = root_privkey.publickey()

    # Generate an RSA public key pair for intermediate CA
    (sub_privkey, sub_pubkey) = crypto.new_rsa_keypair(2048)

    # Encode intermediate tbsCertificate
    sub_tbs = x509.default_tbs(issuer_public_key=root_pubkey,
                               subject_public_key=sub_pubkey,
                               issuer_cn='root',
                               subject_cn='intermediate',
                               is_ca=True,
                               additional_extensions=[],
                               asn=asn)
    for i in range(len(sub_tbs['extensions'])):
        if sub_tbs['extensions'][i]['extnID'] == x509.oid_map['keyUsage']:
            # Replace the key usage extension with one not allowing CRL signing
            sub_tbs['extensions'][i] = x509.key_usage(['keyCertSign'], asn)
    sub_tbs_der = asn.encode('TBSCertificate', sub_tbs)

    # Sign the intermediate tbsCertificate
    sub_sig = crypto.rsa_sha256_sign(root_privkey, sub_tbs_der)
    
    # Encode the intermediate CA Certificate
    sub_cert_der = x509.certificate(sub_tbs, sub_sig, asn)

    # Generate an RSA public key pair for end entity certificate
    (end_privkey, end_pubkey) = crypto.new_rsa_keypair(2048)
    
    # Encode end entity tbsCertificate
    end_tbs = x509.default_tbs(issuer_public_key=sub_pubkey,
                               subject_public_key=end_pubkey,
                               issuer_cn='intermediate',
                               subject_cn='localhost',
                               is_ca=False,
                               additional_extensions=[x509.crl_distribution_points(['http://localhost:49999/crl.der'], asn)],
                               asn=asn)
    end_tbs_der = asn.encode('TBSCertificate', end_tbs)
    
    # Sign the end entity tbsCertificate
    end_sig = crypto.rsa_sha256_sign(sub_privkey, end_tbs_der)
    
    # Encode the end entity Certificate
    end_cert_der = x509.certificate(end_tbs, end_sig, asn)

    # Create the CRL entry
    crl_entry_tbs = x509.revoked_certificate(end_tbs['serialNumber'], 
                                             ('generalTime', misc.current_time()))
    # Create the CRL
    crl_tbs = x509.default_tbs_crl(issuer_public_key=sub_pubkey,
                                   issuer_cn='intermediate',
                                   number=1,
                                   revoked=[crl_entry_tbs],
                                   additional_extensions=[],
                                   asn=asn)
    crl_tbs_der = asn.encode('TBSCertList', crl_tbs)
    crl_sig = crypto.rsa_sha256_sign(sub_privkey, crl_tbs_der)
    crl_der = x509.certificate_list(crl_tbs, crl_sig, asn)

    # Write the chain into file
    io.export_chain([end_cert_der, sub_cert_der], 
                    args.build_dir + EXPORTED_CHAIN_NAME)

    # Write the CRL into file
    io.export_crl(crl_der, args.build_dir + EXPORTED_CRL_NAME)

    # Export the private key
    io.export_private_key(end_privkey, args.build_dir + EXPORTED_KEY_NAME)


if __name__ == "__main__":
    main()
