#!/usr/bin/env python3
"""Module for generating a summary report from various fusion detection tools."""
import argparse
from time import sleep
from lib.db import Db
from lib.page import Page
from lib.report import Report
from lib.section import Section
from lib.graph import Graph
from helpers.tool_parser import ToolParser
from helpers.core import tool_detection_chart, known_vs_unknown_chart, distribution_chart, \
    create_fusions_table, create_ppi_graph, print_progress_bar

# Minimum number of tools that have to detect a fusion, used as a filter in Dashboard
TOOL_DETECTION_CUTOFF = 2

def parse(params):
    """
    Function calling parser of individual tool.

    Args:
        params (ArgumentParser):
    """
    tools = ToolParser()
    tools.parse('ericscript', params.ericscript)
    tools.parse('starfusion', params.starfusion)
    tools.parse('fusioncatcher', params.fusioncatcher)
    tools.parse('pizzly', params.pizzly)
    tools.parse('squid', params.squid)

    return tools

def generate_index(params, parser, known_fusions, unknown_fusions):
    """
    Helper function for generating index.html page.

    Args:
        params (ArgumentParser)
        parser (ToolParser)
        known_fusions (list): List of known fusions
        unknown_fusions (list): List of unknown fusions
    Returns:
        Page: Returns final Page object for index.html page.
    """
    known_sum = len(known_fusions)
    unknown_sum = len(unknown_fusions)
    index_page = Page(
        title='index',
        page_variables={
            'sample': params.sample,
            'fusions_sum': int(unknown_sum + known_sum),
            'known_fusion_sum': known_sum,
            'fusion_tools': parser.get_tools()
        },
        partial_template='index'
    )

    dashboard_section = Section(
        section_id='dashboard',
        title='Dashboard fusion summary'
    )
    dashboard_section.add_graph(
        Graph(
            'tool_detection_chart',
            'Tool detection',
            'Displays number of found fusions per tool.',
            tool_detection_chart(parser.get_tools_count(), parser.get_tools())
        )
    )
    dashboard_section.add_graph(
        Graph(
            'known_vs_unknown_chart',
            'Known Vs Unknown',
            'Shows the ration between found and unknown missing fusions in the local database.',
            known_vs_unknown_chart(known_sum, unknown_sum)
        )
    )
    dashboard_section.add_graph(
        Graph(
            'distribution_chart',
            'Tool detection distribution',
            'Sum of counts detected by different tools per fusion.',
            distribution_chart(parser.get_fusions(), parser.get_tools())
        )
    )
    index_page.add_section(dashboard_section)

    fusion_list_section = Section(
        section_id='fusion_list',
        title='List of detected fusions',
        content='''
            Filters fusions found by at least {tool} tools. If number of chosen tools is less 
            than {tool} the filter is disabled. The whole list can be found in 
            <code>results/Report-{sample}/fusions.txt</code>.
            '''.format(tool=str(params.tool_num), sample=str(params.sample))
    )
    fusion_list_section.data = create_fusions_table(
        parser.get_fusions(),
        parser.get_tools(),
        known_fusions, params.tool_num
    )
    index_page.add_section(fusion_list_section)

    return index_page

def generate_fusion_page(params, parser, fusion, db):
    """
    Helper function for generating <fusion>.html page.

    Args:
        params (ArgumentParser)
        parser (ToolParser)
        fusion (str): name of the fusion geneA--geneB
        db (Db)
    Returns:
        Page: Returns final Page object for <fusion>.html page.
    """
    fusion_page = Page(
        title=fusion,
        page_variables={
            'sample': params.sample,
        },
        partial_template='fusion'
    )
    fusion_pair = fusion.split('--')
    detail_section = Section(
        section_id='details',
        title='Detail results from fusion detection tools',
        content='Some description for each tool?'
    )
    detail_section.data = parser.get_fusion(fusion)
    fusion_page.add_section(detail_section)
    # Variations section
    variations_section = Section(
        section_id='variations',
        title='Fusion gene variations',
        content='''
            Fusion gene information taken from three different sources ChiTars (NAR, 2018), 
            tumorfusions (NAR, 2018) and Gao et al. (Cell, 2018). Genome coordinates are 
            lifted-over GRCh37/hg19 version. <br>Note: LD (Li Ding group, RV: Roel Verhaak group, 
            ChiTaRs fusion database).
        '''
    )
    variations_section.data = db.select(
        '''
        SELECT * FROM TCGA_ChiTaRS_combined_fusion_information_on_hg19
        WHERE h_gene = ? AND t_gene = ?''',
        fusion_pair
    )
    fusion_page.add_section(variations_section)

    transcripts_section = Section(
        section_id='transcripts',
        title='Ensembl transcripts',
        content='''
            Open reading frame (ORF) analsis of fusion genes based on Ensembl gene 
            isoform structure.
        '''
    )
    transcripts_section.data = db.select(
        '''
        SELECT * FROM TCGA_ChiTaRS_combined_fusion_ORF_analyzed_gencode_h19v19
        WHERE h_gene = ? AND t_gene = ?''',
        fusion_pair
    )
    fusion_page.add_section(transcripts_section)

    ppi_section = Section(
        section_id='ppi',
        title='Chimeric Protein-Protein interactions',
        content='''
            Protein-protein interactors with each fusion partner protein in wild-type.
            Data are taken from <a href="http://chippi.md.biu.ac.il/index.html">here</a>
        '''
    )
    ppi_section.data = db.select(
        '''
        SELECT DISTINCT h_gene, h_gene_interactions, t_gene, t_gene_interactions
        FROM fusion_ppi WHERE h_gene = ? AND t_gene = ?''',
        fusion_pair
    )
    ppi_section.add_graph(
        Graph(
            'ppi_graph',
            'Network graph of gene interactions',
            '',
            create_ppi_graph(ppi_section.data)
        )
    )
    fusion_page.add_section(ppi_section)

    drugs_section = Section(
        section_id='targeting_drugs',
        title='Targeting drugs',
        content='''
            Drugs targeting genes involved in this fusion gene 
            (DrugBank Version 5.1.0 2018-04-02).
        '''
    )
    drugs_section.data = db.select(
        '''
        SELECT gene_symbol, drug_status, drug_bank_id, drug_name, drug_action,
        fusion_uniprot_related_drugs.uniprot_acc FROM fusion_uniprot_related_drugs
        INNER JOIN uniprot_gsymbol
        ON fusion_uniprot_related_drugs.uniprot_acc = uniprot_gsymbol.uniprot_acc
        WHERE gene_symbol = ? OR gene_symbol = ?
        ''',
        fusion_pair
    )
    fusion_page.add_section(drugs_section)

    diseases_section = Section(
        section_id='related_diseases',
        title='Related diseases',
        content='Diseases associated with fusion partners (DisGeNet 4.0).'
    )
    diseases_section.data = db.select(
        '''
        SELECT * FROM fgene_disease_associations
        WHERE (gene = ? OR gene = ?)
        AND disease_prob > 0.2001 ORDER BY disease_prob DESC''',
        fusion_pair
    )
    fusion_page.add_section(diseases_section)

    return fusion_page

def generate_report(params):
    """
    Main function for generating report.

    Args:
        params (ArgumentParser)
    """
    parser = parse(params)
    db = Db(params.database)
    known_fusions = []
    unknown_fusions = []
    report = Report(params.config, params.output)

    # Get all fusions from DB
    db.connect('fusiongdb')
    db_fusions = db.select('''
        SELECT DISTINCT (h_gene || "--" || t_gene) as fusion_pair 
        FROM TCGA_ChiTaRS_combined_fusion_information_on_hg19
        ''')
    db_fusions = [x['fusion_pair'] for x in db_fusions]

    fusions = parser.get_fusions()
    print_progress_bar(0, len(fusions), 50)
    for i, fusion in enumerate(fusions):

        if fusion not in db_fusions:
            unknown_fusions.append(fusion)
            # progress bar
            sleep(0.1)
            print_progress_bar(i + 1, len(fusions), 50)
            continue # go to next fusion

        known_fusions.append(fusion)
        fusion_page = generate_fusion_page(params, parser, fusion, db)
        report.add_page(fusion_page)
        # progress bar
        sleep(0.1)
        print_progress_bar(i + 1, len(fusions), 50)

    index_page = generate_index(params, parser, known_fusions, unknown_fusions)
    report.add_page(index_page)
    print(f'The report for `sample` {params.sample} was generated in {params.output}.')

def main():
    """Main function for processing command line arguments"""
    parser = argparse.ArgumentParser(
        description='Tool for generating friendly UI custom report'
    )
    parser.add_argument(
        '--ericscript',
        help='EricScript output file',
        type=str
    )
    parser.add_argument(
        '--fusioncatcher',
        help='FusionCatcher output file',
        type=str
    )
    parser.add_argument(
        '--starfusion',
        help='STAR-Fusion output file',
        type=str
    )
    parser.add_argument(
        '--pizzly',
        help='Pizzly output file',
        type=str
    )
    parser.add_argument(
        '--squid',
        help='Squid output file',
        type=str
    )
    parser.add_argument(
        '-s', '--sample',
        help='Sample name',
        type=str,
        required=True
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory',
        type=str,
        required=True
    )
    parser.add_argument(
        '-c', '--config',
        help='Input config file',
        type=str,
        required=False
    )
    parser.add_argument(
        '-t', '--tool_num',
        help='Number of tools required to detect a fusion',
        type=int,
        default=TOOL_DETECTION_CUTOFF
    )
    parser.add_argument(
        '-db', '--database',
        help='Path to database file fusions.db (for local development)',
        type=str,
        required=False
    )
    generate_report(parser.parse_args())

if __name__ == "__main__":
    main()